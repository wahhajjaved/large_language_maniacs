import numpy as np
import pandas as pd
from geopy.distance import vincenty
from mpl_toolkits.basemap import Basemap
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.pylab as plt
from atmPy.general import timeseries
from pyhdf.SD import SD, SDC
from matplotlib.colors import LinearSegmentedColormap


def get_cmap(norm='linear', log_min=None, reverse=False):
    colors = np.array([np.array([0.0, 4., 76.]) / 255.,
                       np.array([49., 130., 0.0]) / 255.,
                       np.array([255, 197., 98.]) / 255.,
                       np.array([245., 179., 223.]) / 255.,
                       np.array([1, 1, 1]),
                       ])

    if norm == 'linear':
        steps = np.logspace(0, 1, len(colors))
    elif norm == 'log':
        steps = np.logspace(log_min, 0, len(colors))
        steps[0] = 0

    if reverse:
        colors = colors[::-1]

    r = np.zeros((len(colors), 3))
    r[:, 0] = steps
    r[:, 1] = colors[:, 0]
    r[:, 2] = colors[:, 0]

    g = np.zeros((len(colors), 3))
    g[:, 0] = steps
    g[:, 1] = colors[:, 1]
    g[:, 2] = colors[:, 1]

    b = np.zeros((len(colors), 3))
    b[:, 0] = steps
    b[:, 1] = colors[:, 2]
    b[:, 2] = colors[:, 2]

    cdict = {'red': r,
             'green': g,
             'blue': b
             }

    hag_cmap = LinearSegmentedColormap('hag_cmap', cdict)
    hag_cmap.set_bad('black')
    return hag_cmap


def read_file(fname):
    out = Calipso(fname)
    return out



def get_total_attenuated_backscattering(hdf, datetime, bins):
    totattback = hdf.select('Total_Attenuated_Backscatter_532')
    data = totattback[:]
    data[data == -9999.0] = np.nan
    totbackatt_df = pd.DataFrame(data, index=datetime, columns=bins)
    #     ts = timeseries.TimeSeries_2D(totbackatt_df)
    ts = Total_Attenuated_Backscattering(totbackatt_df)
    return ts

def generate_altitude_data(level = 1):
    if level != 1:
        raise ValueError('not implemented yet')
    # list taken from https://www-calipso.larc.nasa.gov/resources/calipso_users_guide/data_summaries/l1b/index.php#Table01
    layer_list = [{'alt_layerbottom': 30.1 * 1e3, 'start_bin': 1, 'end_bin':33, 'v_resolution': 300, 'h_resolution': 5000},
                  {'alt_layerbottom': 20.2 * 1e3, 'start_bin': 34, 'end_bin':88, 'v_resolution': 180, 'h_resolution': 5/3 * 1e3},
                  {'alt_layerbottom': 8.3 * 1e3,  'start_bin': 89, 'end_bin':288, 'v_resolution': 60, 'h_resolution': 1000},
                  {'alt_layerbottom': -0.5 * 1e3, 'start_bin': 289, 'end_bin':578, 'v_resolution': 30, 'h_resolution': 300},
                  {'alt_layerbottom': -2 * 1e3, 'start_bin': 579, 'end_bin':583, 'v_resolution': 300, 'h_resolution': 300}
                 ]
    layer_data = pd.DataFrame(layer_list)

    bins = np.zeros(583)

    top_of_layer = 40* 1e3
    for index, row in layer_data.iterrows():
        start = int(row['start_bin']-1)
        end = int(row['end_bin'])
        shape = bins[start :end].shape[0]
        new_bins  = np.linspace(row['alt_layerbottom'], top_of_layer, shape, endpoint=False)[::-1]
        top_of_layer = row['alt_layerbottom']
        layer_thickness = (new_bins[:-1] - new_bins[1:]).mean()
        bins[start :end] = new_bins
    #     bins[start :end] =  row['alt_layerbottom'] + (np.arange(bins[start :end].shape[0]) * row['v_resolution'])[::-1]
    return bins


# def plot_on_map(self, projection='aeqd', resolution = 'c', points_of_interest = None, three_d=False):
#     """Plots a map of the flight path
#
#     Note
#     ----
#     packages: matplotlib-basemap,
#
#     Arguments
#     ---------
#     three_d: bool.
#         If flight path is plotted in 3D. unfortunately this does not work very well (only costlines)
#     """
#
#     data = self.data.copy()
#     data = data.loc[:,['Lon','Lat']]
#     data = data.dropna()
#
#     lon_center = (data.Lon.values.max() + data.Lon.values.min()) / 2.
#     lat_center = (data.Lat.values.max() + data.Lat.values.min()) / 2.
#
#     points = np.array([data.Lat.values, data.Lon.values]).transpose()
#     distances_from_center_lat = np.zeros(points.shape[0])
#     distances_from_center_lon = np.zeros(points.shape[0])
#     for e, p in enumerate(points):
#         distances_from_center_lat[e] = vincenty(p, (lat_center, p[1])).m
#         distances_from_center_lon[e] = vincenty(p, (p[0], lon_center)).m
#
#     lat_radius = distances_from_center_lat.max()
#     lon_radius = distances_from_center_lon.max()
#     scale = 1
#     border = scale * 2 * np.array([lat_radius, lon_radius]).max()
#
#     height = border + lat_radius
#     width = border + lon_radius
#     if not three_d:
#         if projection == 'mill':
#             bmap = Basemap(projection='mill',llcrnrlat=-90,urcrnrlat=90,\
#                 llcrnrlon=-180,urcrnrlon=180,resolution='c')
#
#         elif projection == 'aeqd':
#             bmap = Basemap(projection=projection,
#                            lat_0=lat_center,
#                            lon_0=lon_center,
#                            width=width,
#                            height=height,
#                            resolution=resolution)
#         else:
#             raise ValueError('projection ')
#         # Fill the globe with a blue color
#         wcal = np.array([161., 190., 255.]) / 255.
#         boundary = bmap.drawmapboundary(fill_color=wcal)
#
#         grau = 0.9
#         continents = bmap.fillcontinents(color=[grau, grau, grau], lake_color=wcal)
#         costlines = bmap.drawcoastlines()
#         x, y = bmap(data.Lon.values, data.Lat.values)
#         path = bmap.plot(x, y,
#                          color='m')
#
# #         return bmap
#
#     else:
#         bmap = Basemap(projection=projection,
#                    lat_0=lat_center,
#                    lon_0=lon_center,
#                    width=width,
#                    height=height,
#                    resolution=resolution)
#
#         fig = plt.figure()
#         ax = Axes3D(fig)
#         ax.add_collection3d(bmap.drawcoastlines())
#         x, y = bmap(self.data.Lon.values, self.data.Lat.values)
#         # ax.plot(x, y,self.data.Altitude.values,
#         #           color='m')
#         N = len(x)
#         for i in range(N - 1):
#             color = plt.cm.jet(i / N)
#             ax.plot(x[i:i + 2], y[i:i + 2], self.data.Altitude.values[i:i + 2],
#                     color=color)
#     if points_of_interest:
#         for point in points_of_interest:
#
#             lat,lon = point.pop('loc_lat_lon')
#             x,y = bmap(lon,lat)
#             ax = plt.gca()
#
#             try:
#                 annotation = point.pop('annotation')
#                 annotation_kwargs = point.pop('annotations_kwargs')
#             except KeyError:
#                 annotation = None
#
#
#             g, = bmap.plot(x,y)
#             g.set(**point)
#
#             if annotation:
#                 anno = ax.annotate(annotation, (x,y), **annotation_kwargs)
#     return bmap

def plot_on_map(self, bmap_kwargs=None, estimate_extend=True, costlines = True, continents = True, background = None, points_of_interest=None, three_d=False, verbose = False):
    """

    Args:
        bmap_kwargs:
        estimate_extend:
        costlines:
        background: str [None]
            options are 'bluemarble', 'shadedrelief', 'etopo'
        points_of_interest:
        three_d:
        verbose:

    Returns:

    """

    data = self.data.copy()
    data = data.loc[:, ['Lon', 'Lat']]
    data = data.dropna()

    if not bmap_kwargs:
        bmap_kwargs = {'projection': 'aeqd',
                       'resolution': 'c'}

    if estimate_extend:
        if bmap_kwargs['projection'] == 'aeqd':
            lon_center = (data.Lon.values.max() + data.Lon.values.min()) / 2.
            lat_center = (data.Lat.values.max() + data.Lat.values.min()) / 2.

            points = np.array([data.Lat.values, data.Lon.values]).transpose()
            distances_from_center_lat = np.zeros(points.shape[0])
            distances_from_center_lon = np.zeros(points.shape[0])
            for e, p in enumerate(points):
                distances_from_center_lat[e] = vincenty(p, (lat_center, p[1])).m
                distances_from_center_lon[e] = vincenty(p, (p[0], lon_center)).m

            lat_radius = distances_from_center_lat.max()
            lon_radius = distances_from_center_lon.max()
            scale = 1
            border = scale * 2 * np.array([lat_radius, lon_radius]).max()

            height = border + lat_radius
            width = border + lon_radius
            bmap_kwargs['lat_0'] = lat_center
            bmap_kwargs['lon_0'] = lon_center
            bmap_kwargs['width'] = width
            bmap_kwargs['height'] = height

        elif bmap_kwargs['projection'] == 'mill':
            bmap_kwargs['llcrnrlat'] = -90
            bmap_kwargs['urcrnrlat'] = 90
            bmap_kwargs['llcrnrlon'] = -180
            bmap_kwargs['urcrnrlon'] = 180

        if verbose:
            print('bmap_kwargs: {}'.format(bmap_kwargs))

    bmap = Basemap(**bmap_kwargs)
    if not three_d:
        wcal = np.array([161., 190., 255.]) / 255.

        if background == 'bluemarbel':
            bmap.bluemarble()
        elif background == 'etopo':
            bmap.etopo()
        elif background == 'shadedrelief':
            bmap.shadedrelief()
        elif not background:
            # Fill the globe with a blue color
            bmap.drawmapboundary(fill_color=wcal)
        else:
            raise ValueError('"{}" is not a valid background!'.format(background))

        if continents:
            grau = 0.9
            bmap.fillcontinents(color=[grau, grau, grau], lake_color=wcal)

        if costlines:
            bmap.drawcoastlines()

        x, y = bmap(data.Lon.values, data.Lat.values)
        path = bmap.plot(x, y,
                         color='m')

    # return bmap

    else:
        fig = plt.figure()
        ax = Axes3D(fig)
        ax.add_collection3d(bmap.drawcoastlines())
        x, y = bmap(self.data.Lon.values, self.data.Lat.values)
        # ax.plot(x, y,self.data.Altitude.values,
        #           color='m')
        N = len(x)
        for i in range(N - 1):
            color = plt.cm.jet(i / N)
            ax.plot(x[i:i + 2], y[i:i + 2], self.data.Altitude.values[i:i + 2],
                    color=color)

    if points_of_interest:
        for point in points_of_interest:

            lat, lon = point.pop('loc_lat_lon')
            x, y = bmap(lon, lat)
            ax = plt.gca()

            try:
                annotation = point.pop('annotation')
                annotation_kwargs = point.pop('annotations_kwargs')
            except KeyError:
                annotation = None

            g, = bmap.plot(x, y)
            g.set(**point)

            if annotation:
                anno = ax.annotate(annotation, (x, y), **annotation_kwargs)
    return bmap


def get_closest2location(path, location):
    """
    Args
    ----
    location: tuple
        (lat,lon)"""

    def get_dist(row, location):
        """
        Args
        ----
        location: tuple
            (lat,lon)
            """
        dist = vincenty(location, (row['Lat'], row['Lon']))
        #     print(row)
        return dist.km

    get_distance2location(path, location)
    data = path.data.copy()
    closest = data.sort_values('distance').iloc[[0]]
    return closest


def get_distance2location(path, location):
    """Ads a collumn to path.data.
    Args
    ----
    location: tuple
        (lat,lon)"""

    def get_dist(row, location):
        """
        Args
        ----
        location: tuple
            (lat,lon)
            """
        dist = vincenty(location, (row['Lat'], row['Lon']))
        #     print(row)
        return dist.km

    dist = path.data.apply(lambda x: get_dist(x, location), axis=1)
    path.data['distance'] = dist
    return


def get_path(hdf, datetime):
    lon = hdf.select('Longitude')[:][:, 0]
    lat = hdf.select('Latitude')[:][:, 0]
    loc_ts = Path(pd.DataFrame({'Lon': lon, 'Lat': lat}, index=datetime))
    return loc_ts

def get_datetime(hdf):
    time = hdf.select('Profile_UTC_Time')
    time.dimensions()
    td = time[:].transpose()[0]
    day, date = np.modf(td)
    datetime = pd.to_datetime(date.astype(int), format = '%y%m%d') + pd.to_timedelta(day, unit='d')
    return datetime

class Path(timeseries.TimeSeries):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._closest_location = None
        self._closest = None
        self._radius = None
        self._in_radius = None

    plot_on_map = plot_on_map

    def get_closest2location(self, location):
        if location == self._closest_location:
            return self._closest
        else:
            self._closest_location = location
            self._closest = get_closest2location(self, location)
            return self._closest

    def get_all_in_radius(self, location, radius):
        self.get_closest2location(location)
        if (location != self._closest_location) or (radius != self._radius):
            self._closest_location = location
            self._radius = radius
            self._in_radius = self.data.distance <= radius
        return self._in_radius


class Total_Attenuated_Backscattering(timeseries.TimeSeries_2D):
    def plot(self, *args, **kwargs):
        f, a, pc, cb = super().plot(*args, **kwargs)
        a.set_ylabel('Altitude (m)')
        a.set_xlabel('')
        if cb:
            cb.set_label('Total attenuated backscattering')
        return f, a, pc, cb




class Calipso(object):
    def __init__(self, fname):
        self._hdf = SD(fname, SDC.READ)
        self._reset()
        self._inradius = None
        self._ts = None
        self._bs = None

    #         self._zoom_d = None

    def _reset(self):
        self._path = None
        self._totattback = None


    @property
    def _timestamps(self):
        if type(self._ts).__name__ == 'NoneType':
            self._ts = get_datetime(self._hdf)
            # if type(self._inradius).__name__ != 'NoneType':
            #     self._ts = self._ts[self._inradius]
        return self._ts

    @property
    def _bins(self):
        if type(self._bs).__name__ == 'NoneType':
            self._bs = generate_altitude_data(level = 1)
        return self._bs

    @property
    def total_attenuated_backscattering(self):
        if not self._totattback:
            self._totattback = get_total_attenuated_backscattering(self._hdf, self._timestamps, self._bins)
            if type(self._inradius).__name__ != 'NoneType':
                self._totattback = Total_Attenuated_Backscattering(self._totattback.data[self._inradius])
        return self._totattback

    #     @total_attenuated_backscattering.setter
    #     def total_attenuated_backscattering(self,value):
    #         self._totattback = Total_Attenuated_Backscattering(value)

    @property
    def path(self):
        if not self._path:
            self._path = get_path(self._hdf, self._timestamps)
            if type(self._inradius).__name__ != 'NoneType':
                self._path = Path(self._path.data[self._inradius])
                #             if self._zoom:
                #                 self._path.data
        return self._path

    #     @path.setter
    #     def path(self,value):
    #         self._path = Path(value)

    def limit2location(self, location, radius):
        """This will limit all data to data that is in a certain radius around a location"""
        self._inradius = self.path.get_all_in_radius(location, radius)
        self._reset()

# if self._path:
#             self.path = self.path.data[inradius]
#         if self._totattback:
#             self.total_attenuated_backscattering = self.total_attenuated_backscattering.data[inradius]
#         if self._ts:
#             self._timestamps = self._timestamps[inradius]

