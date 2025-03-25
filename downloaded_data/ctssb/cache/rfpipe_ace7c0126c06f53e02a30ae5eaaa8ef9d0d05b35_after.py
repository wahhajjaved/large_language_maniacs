from __future__ import print_function, division, absolute_import, unicode_literals
from builtins import bytes, dict, object, range, map, input, str
from future.utils import itervalues, viewitems, iteritems, listvalues, listitems
from io import open

import pickle
import os
from copy import deepcopy
import numpy as np
from math import cos, radians
from numpy.lib.recfunctions import append_fields
from collections import OrderedDict
import matplotlib as mpl
from astropy import time
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from rfpipe import version, fileLock, state
from bokeh.plotting import ColumnDataSource, Figure, save, output_file
from bokeh.models import HoverTool
from bokeh.models import Row
from collections import OrderedDict
import hdbscan

import logging
logger = logging.getLogger(__name__)


class CandData(object):
    """ Object that bundles data from search stage to candidate visualization.
    Provides some properties for the state of the phased data and candidate.
    """

    def __init__(self, state, loc, image, data, **kwargs):
        """ Instantiate with pipeline state, candidate location tuple,
        image, and resampled data phased to candidate.
        TODO: Need to use search_dimensions to infer candloc meaning
        """

        self.state = state
        self.loc = tuple(loc)
        self.image = image
        self.data = data
        if 'snrk' in kwargs:  # hack to allow detection level calculation in
            self.snrk = kwargs['snrk']
        else:
            self.snrk = None
        if 'snrarms' in kwargs:  # hack to allow detection level calculation in
            self.snrarms = kwargs['snrarms']
        else:
            self.snrarms = None
        if 'cluster' in kwargs:
            self.cluster = kwargs['cluster']
        else:
            self.cluster = None
        if 'clustersize' in kwargs:
            self.clustersize = kwargs['clustersize']
        else:
            self.clustersize = None

        assert len(loc) == len(state.search_dimensions), ("candidate location "
                                                          "should set each of "
                                                          "the st.search_dimensions")

    def __repr__(self):
        return 'CandData for scanId {0} at loc {1}'.format(self.state.metadata.scanId, self.loc)

    @property
    def snrtot(self):
        """ Optimal SNR given searchtype (e.g., snr1 with snrk, if snrk measured)
        """

        if self.state.prefs.searchtype == 'image':
            return self.snr1
        elif self.state.prefs.searchtype == 'imagek':
            return (self.snrk**2 + self.snr1**2)**0.5
        elif self.state.prefs.searchtype == 'armkimage':
            return (self.snrk**2 + self.snr1**2)**0.5
        elif self.state.prefs.searchtype == 'armk':
            return (self.snrk**2 + self.snrarms**2)**0.5

    @property
    def snr1(self):
        return self.image.max()/self.image.std()

    @property
    def integration_rel(self):
        """ Candidate integration relative to data time window
        """

        if self.loc[1] < self.state.prefs.timewindow//2:
            return self.loc[1]
        else:
            return self.state.prefs.timewindow//2

    @property
    def peak_lm(self):
        """
        """

        return self.state.pixtolm(self.peak_xy)

    @property
    def peak_xy(self):
        """ Peak pixel in image
        Only supports positive peaks for now.
        """

        return np.where(self.image == self.image.max())

    @property
    def time_top(self):
        """ Time in mjd where burst is at top of band
        """

        return (self.state.segmenttimes[self.loc[0]][0] +
                (self.loc[1]*self.state.inttime)/(24*3600))


class CandCollection(object):
    """ Wrap candidate array with metadata and
    prefs to be attached and pickled.
    """

    def __init__(self, array=np.array([]), prefs=None, metadata=None):
        self.array = array
        self.prefs = prefs
        self.metadata = metadata
        self.rfpipe_version = version.__version__
        self._state = None
        # TODO: pass in segmenttimes here to avoid recalculating during search?

    def __repr__(self):
        if self.metadata is not None:
            return ('CandCollection for {0}, scan {1} with {2} candidate{3}'
                    .format(self.metadata.datasetId, self.metadata.scan,
                            len(self), 's'[not len(self)-1:]))
        else:
            return ('CandCollection with {0} rows'.format(len(self.array)))

    def __len__(self):
        return len(self.array)

    def __add__(self, cc):
        """ Allow candcollections to be added within a given scan.
        (same dmarr, dtarr, segmenttimes)
        Adding empty cc ok, too.
        """

        if len(cc):
            # TODO: update to allow different simulated_transient fields that get added into single list
            assert self.prefs.name == cc.prefs.name, "Cannot add collections with different preferences"
            assert self.state.dmarr == cc.state.dmarr,  "Cannot add collections with different dmarr"
            assert self.state.dtarr == cc.state.dtarr,  "Cannot add collections with different dmarr"
            assert (self.state.segmenttimes == cc.state.segmenttimes).all(),  "Cannot add collections with different segmenttimes"
            if len(self):
                self.array = np.concatenate((self.array, cc.array))
            else:
                self.array = cc.array
        return self

    def __getitem__(self, key):
        return CandCollection(array=self.array.take([key]), prefs=self.prefs,
                              metadata=self.metadata)

    @property
    def scan(self):
        if self.metadata is not None:
            return self.metadata.scan
        else:
            return None

    @property
    def segment(self):
        if len(self.array):
            segments = np.unique(self.array['segment'])
            if len(segments) == 1:
                return int(segments[0])
            elif len(segments) > 1:
                logger.warn("Multiple segments in this collection")
                return segments
            else:
                logger.warn("No candidates in this collection")
                return None
        else:
            return None

    @property
    def locs(self):
        if len(self.array):
            return self.array[['segment', 'integration', 'dmind', 'dtind',
                               'beamnum']].tolist()
        else:
            return np.array([], dtype=int)

    @property
    def candmjd(self):
        """ Candidate MJD at top of band
        """

#        dt_inf = util.calc_delay2(1e5, self.state.freq.max(), self.canddm)
        t_top = np.array(self.state.segmenttimes)[self.array['segment'], 0] + (self.array['integration']*self.canddt)/(24*3600)

        return t_top

    @property
    def canddm(self):
        """ Candidate DM in pc/cm3
        """

        dmarr = np.array(self.state.dmarr)
        return dmarr[self.array['dmind']]

    @property
    def canddt(self):
        """ Candidate dt in seconds
        """

        dtarr = np.array(self.state.dtarr)
        return self.metadata.inttime*dtarr[self.array['dtind']]

    @property
    def candl(self):
        """ Return l1 for candidate (offset from phase center in RA direction)
        """
        #  beamnum not yet supported

        return self.array['l1']

    @property
    def candm(self):
        """ Return m1 for candidate (offset from phase center in Dec direction)
        """
        #  beamnum not yet supported

        return self.array['m1']

    @property
    def cluster(self):
        """ Return cluster label
        """

        if self.prefs.clustercands:
            return self.array['cluster']
        else:
            return None

    @property
    def clustersize(self):
        """ Return size of cluster
        """

        if self.prefs.clustercands:
            return self.array['clustersize']
        else:
            return None

    @property
    def snrtot(self):
        """ Optimal SNR given searchtype (e.g., snr1 with snrk, if snrk measured)
        """

        if self.prefs.searchtype == 'image':
            return self.array['snr1']
        elif self.prefs.searchtype == 'imagek':
            return (self.array['snrk']**2 + self.array['snr1']**2)**0.5
        elif self.prefs.searchtype == 'armkimage':
            return (self.array['snrk']**2 + self.array['snr1']**2)**0.5
        elif self.prefs.searchtype == 'armk':
            return (self.array['snrk']**2 + self.array['snrarms']**2)**0.5

    @property
    def state(self):
        """ Sets state by regenerating from the metadata and prefs.
        """

        if self._state is None:
            self._state = state.State(inmeta=self.metadata, inprefs=self.prefs,
                                      showsummary=False, validate=False)

        return self._state

    def sdmname(self):
        """ Get name of SDM created by realfast based on naming convention
        """

        segment = self.segment
        segmenttimes = self.state.segmenttimes
        startTime = segmenttimes[segment][0]
        bdftime = int(time.Time(startTime, format='mjd').unix*1e3)
        return 'realfast_{0}_{1}'.format(self.state.metadata.datasetId, bdftime)


def save_and_plot(canddatalist):
    """ Converts a canddata list into a plots and a candcollection.
    Calculates candidate features from CandData instance(s).
    Returns structured numpy array of candidate features labels defined in
    st.search_dimensions.
    Generates png plot for peak cands, if so defined in preferences.
    """

    if isinstance(canddatalist, CandData):
        canddatalist = [canddatalist]
    elif isinstance(canddatalist, list):
        if not len(canddatalist):
            return CandCollection()
    else:
        logger.warn("argument must be list of CandData object")

    logger.info('Calculating features for {0} candidate{1}.'
                .format(len(canddatalist), 's'[not len(canddatalist)-1:]))

    st = canddatalist[0].state

    featurelists = []
    for feature in st.features:
        ff = []
        for i, canddata in enumerate(canddatalist):
            ff.append(canddata_feature(canddata, feature))
        featurelists.append(ff)
    kwargs = dict(zip(st.features, featurelists))

    candlocs = []
    for i, canddata in enumerate(canddatalist):
        candlocs.append(canddata_feature(canddata, 'candloc'))
        kwargs['candloc'] = candlocs

    if canddata.cluster is not None:
        clusters = []
        clustersizes = []
        for i, canddata in enumerate(canddatalist):
            clusters.append(canddata_feature(canddata, 'cluster'))
            clustersizes.append(canddata_feature(canddata, 'clustersize'))
        kwargs['cluster'] = clusters
        kwargs['clustersize'] = clustersizes

    candcollection = make_candcollection(st, **kwargs)

    if (st.prefs.savecands or st.prefs.saveplots) and len(candcollection.array):
        if len(candcollection) > 1:
            snrs = candcollection.array['snr1'].flatten()
        elif len(candcollection) == 1:
            snrs = None

        # save cc and save/plot each canddata
        for i, canddata in enumerate(canddatalist):
            if st.prefs.savecands:
                save_cands(st, canddata=canddata)
            if st.prefs.saveplots:
                candplot(canddata, cluster=(clusters[i], clustersizes[i]), snrs=snrs)

    return candcollection


def canddata_feature(canddata, feature):
    """ Calculate a feature (or candloc) from a canddata instance.
    feature must be name from st.features or 'candloc'.
    """

    st = canddata.state
    image = canddata.image
    dataph = canddata.data
    candloc = canddata.loc

    if feature == 'candloc':
        return candloc
    elif feature == 'snr1':
# TODO: find good estimate for both CPU and GPU
#       imstd = util.madtostd(image)  # outlier resistant
        imstd = image.std()  # consistent with rfgpu
        logger.debug('{0} {1}'.format(image.shape, imstd))
        snrim = image.max()/imstd
        return snrim
    elif feature == 'snrarms':
        return canddata.snrarms
    elif feature == 'snrk':
        return canddata.snrk
    elif feature == 'cluster':
        return canddata.cluster
    elif feature == 'clustersize':
        return canddata.clustersize
    elif feature == 'immax1':
        return image.max()
    elif feature == 'l1':
        l1, m1 = st.pixtolm(np.where(image == image.max()))
        return float(l1)
    elif feature == 'm1':
        l1, m1 = st.pixtolm(np.where(image == image.max()))
        return float(m1)
    else:
        raise NotImplementedError("Feature {0} calculation not implemented"
                                  .format(feature))


def make_candcollection(st, **kwargs):
    """ Construct a candcollection with columns set by keywords.
    Minimal cc has a candloc (segment, int, dmind, dtind, beamnum).
    Can also provide features as keyword/value pairs.
    keyword is the name of the column (e.g., "l1", "snr")
    and the value is a list of values of equal length as candlocs.
    """

    if len(kwargs):
        # assert 1-to-1 mapping of input lists
        assert 'candloc' in kwargs
        assert isinstance(kwargs['candloc'], list)
        for v in itervalues(kwargs):
            assert len(v) == len(kwargs['candloc'])

        candlocs = kwargs['candloc']
        features = [kw for kw in list(kwargs.keys())]
        features.remove('candloc')
        fields = []
        types = []
        for ff in st.search_dimensions + tuple(features):
            fields.append(str(ff))
            if ff in st.search_dimensions + ('cluster', 'clustersize'):
                tt = '<i4'
            else:
                tt = '<f4'
            types.append(str(tt))

        dtype = np.dtype({'names': fields, 'formats': types})
        array = np.zeros(len(candlocs), dtype=dtype)
        for i in range(len(candlocs)):
            ff = list(candlocs[i])
            for feature in features:
                ff.append(kwargs[feature][i])

            array[i] = tuple(ff)
        candcollection = CandCollection(array=array, prefs=st.prefs,
                                        metadata=st.metadata)
    else:
        candcollection = CandCollection(prefs=st.prefs,
                                        metadata=st.metadata)

    return candcollection


def cluster_candidates(cc, returnclusterer=False, label_unclustered=True):
    """ Perform density based clustering on candidates using HDBSCAN
    parameters used for clustering: dm, time, l,m.
    label_unclustered adds new cluster label for each unclustered candidate.
    Returns label for each row in candcollection.
    """

    cc1 = deepcopy(cc)
    if len(cc1) > 1:
        if isinstance(cc1.prefs.clustercands, tuple):
            min_cluster_size, min_samples = cc1.prefs.clustercands
        elif isinstance(cc1.prefs.clustercands, bool):
            if cc1.prefs.clustercands:
                min_cluster_size = 3
                min_samples = 2
            else:
                logger.info("Not performing clustering")
                return cc1
        else:
            logger.warn("No clustering. prefs.clustercands value not valid: {0}."
                        .format(cc1.prefs.clustercands))
            return cc1

        logger.info("Clustering parameters set to ({0},{1})."
                    .format(min_cluster_size, min_samples))

        if min_cluster_size > len(cc1):
            logger.info("Setting min_cluster_size to number of cands {0}"
                        .format(len(cc1)))
            min_cluster_size = len(cc1)
        candl = cc1.candl
        candm = cc1.candm
        npixx = cc1.state.npixx
        npixy = cc1.state.npixy
        uvres = cc1.state.uvres

        peakx_ind, peaky_ind = cc1.state.calcpix(candl, candm, npixx, npixy,
                                                 uvres)

        dm_ind = cc1.array['dmind']
        dtind = cc1.array['dtind']
        dtarr = cc1.state.dtarr
        timearr_ind = cc1.array['integration']  # time index of all the candidates
        time_ind = np.multiply(timearr_ind, np.array(dtarr).take(dtind))
        data = np.transpose([peakx_ind, peaky_ind, dm_ind, time_ind])

        clusterer = hdbscan.HDBSCAN(metric='hamming',
                                    min_cluster_size=min_cluster_size,
                                    min_samples=min_samples,
                                    cluster_selection_method='eom',
                                    allow_single_cluster=True).fit(data)
        nclustered = np.max(clusterer.labels_ + 1)
        nunclustered = len(np.where(clusterer.labels_ == -1)[0])

        logger.info("Found {0} clusters and {1} unclustered candidates for "
                    "min cluster size {2}"
                    .format(nclustered, nunclustered, min_cluster_size))

        labels = clusterer.labels_.astype(np.int32)
    else:
        clusterer = None
        labels = -1*np.ones(len(cc1), dtype=np.int32)

    if -1 in labels and label_unclustered:
        unclustered = np.where(labels == -1)[0]
        logger.info("Adding {0} unclustered candidates as individual clusters"
                    .format(len(unclustered)))
        newind = max(labels)
        for cli in unclustered:
            newind += 1
            labels[cli] = newind

    # TODO: rebuild array with new col or accept broken python 2 or create cc with 'cluster' set to -1
    if 'cluster' not in cc1.array.dtype.fields:
        cc1.array = append_fields(cc1.array, 'cluster', labels, usemask=False)
    else:
        cc1.array['cluster'] = labels

    if returnclusterer:
        return cc1, clusterer
    else:
        return cc1


def calc_cluster_rank(cc):
    """ Given cluster array of candcollection, calculate rank relative
    to total count in each cluster.
    Rank ranges from 1 (highest SNR in cluster) to total count in cluster.
    """

    assert 'cluster' in cc.array.dtype.fields

    # get count in cluster and snr rank of each in its cluster
    clusters = cc.array['cluster'].astype(int)
    cl_rank = np.zeros(len(clusters), dtype=int)
    cl_count = np.zeros(len(clusters), dtype=int)

    # TODO: check on best way to find max SNR with kalman, etc
    for cluster in np.unique(clusters):
        clusterinds = np.where(cluster == clusters)[0]
        snrs = cc.array['snr1'][clusterinds]
        cl_rank[clusterinds] = np.argsort(np.argsort(snrs)[::-1])+1 
        cl_count[clusterinds] = len(clusterinds)

    return cl_rank, cl_count


def save_cands(st, candcollection=None, canddata=None):
    """ Save candidate collection or cand data to pickle file.
    Collection saved as array with metadata and preferences attached.
    Writes to location defined by state using a file lock to allow multiple
    writers.
    """

    if canddata is not None:
        if st.prefs.savecands:
            logger.info('Saving CandData to {0}.'.format(st.candsfile))

            try:
                with fileLock.FileLock(st.candsfile+'.lock', timeout=10):
                    with open(st.candsfile, 'ab+') as pkl:
                        pickle.dump(canddata, pkl)
            except fileLock.FileLock.FileLockException:
                segment = canddata.loc[0]
                newcandsfile = ('{0}_seg{1}.pkl'
                                .format(st.candsfile.rstrip('.pkl'), segment))
                logger.warn('Candidate file writing timeout. '
                            'Spilling to new file {0}.'.format(newcandsfile))
                with open(newcandsfile, 'ab+') as pkl:
                    pickle.dump(canddata, pkl)

        else:
            logger.info('Not saving CandData.')

    if candcollection is not None:
        if st.prefs.savecands and len(candcollection):
            logger.info('Saving {0} candidate{1} to {2}.'
                        .format(len(candcollection),
                                's'[not len(candcollection)-1:], st.candsfile))

            try:
                with fileLock.FileLock(st.candsfile+'.lock', timeout=10):
                    with open(st.candsfile, 'ab+') as pkl:
                        pickle.dump(candcollection, pkl)
            except fileLock.FileLock.FileLockException:
                segment = candcollection.segment
                newcandsfile = ('{0}_seg{1}.pkl'
                                .format(st.candsfile.rstrip('.pkl'), segment))
                logger.warn('Candidate file writing timeout. '
                            'Spilling to new file {0}.'.format(newcandsfile))
                with open(newcandsfile, 'ab+') as pkl:
                    pickle.dump(candcollection, pkl)

        elif st.prefs.savecands and not len(candcollection.array):
            logger.debug('No candidates to save to {0}.'.format(st.candsfile))

        elif not st.prefs.savecands:
            logger.info('Not saving candidates.')


def iter_cands(candsfile, select='candcollection'):
    """ Iterate through (new style) candsfile and return either
    a candidatecollection or canddata.
    select defines what kind of object to return:
    - 'canddata' is heavier object with image and spectrum (used to make plots)
    - 'candcollection' is lighter object with features.
    """

    assert select.lower() in ['candcollection', 'canddata']

    try:
        with open(candsfile, 'rb') as pkl:
            while True:  # step through all possible segments
                try:
                    candobj = pickle.load(pkl)
                    if select.lower() in str(type(candobj)).lower():
                        yield candobj
                except EOFError:
                    logger.debug('Reached end of pickle.')
                    break
    except UnicodeDecodeError:
        with open(candsfile, 'rb') as pkl:
            while True:  # step through all possible segments
                try:
                    candobj = pickle.load(pkl, encoding='latin-1')
                    if select.lower() in str(type(candobj)).lower():
                        yield candobj
                except EOFError:
                    logger.debug('Reached end of pickle.')
                    break


def iter_noise(noisefile):
    """ Iterate through (new style) noisefile and return a list of tuples
    for each segment.
    """

    try:
        with open(noisefile, 'rb') as pkl:
            while True:  # step through all possible segments
                try:
                    noises = pickle.load(pkl)
                    for noise in noises:
                        yield noise

                except EOFError:
                    logger.debug('No more CandCollections.')
                    break
    except UnicodeDecodeError:
        with open(noisefile, 'rb') as pkl:
            while True:  # step through all possible segments
                try:
                    noises = pickle.load(pkl, encoding='latin-1')
                    for noise in noises:
                        yield noise

                except EOFError:
                    logger.debug('No more CandCollections.')
                    break


### bokeh summary plot

def cluster_plotting_bokeh(candcollection, clusterer):
    """to be modified if needed!
    Generates bokeh plots of various parameters for visualising clustering
    """

    from bokeh.layouts import row, column
    import seaborn as sns

    cc = candcollection

    color_palette = sns.color_palette('deep', np.max(clusterer.labels_) + 1) #get a color palette with number
    cluster_colors = [color_palette[x] if x >= 0
                      else (0.5, 0.5, 0.5)
                      for x in clusterer.labels_]    #assigning each cluster a color, and making a list of equal length

    cluster_member_colors = [sns.desaturate(x, p) for x, p in
                             zip(cluster_colors, clusterer.probabilities_)]

    cluster_colors = list(map(mpl.colors.rgb2hex, cluster_member_colors)) #converting sns colors to hex for bokeh

    width = 450
    height = 350
    output_notebook()

    TOOLS = 'crosshair, box_zoom, reset, box_select, tap, hover, wheel_zoom'
#data = dict(l= peakx_ind, m= peaky_ind, dm= dm_ind, time= time_ind, snr= snr, colors = cluster_colors)
    data = dict(l= candl, m= candm, dm= canddm, time= time_ind, snr= snr, colors = cluster_colors)
    source=ColumnDataSource(data=data)

    p = figure(title="m vs l", x_axis_label='l', y_axis_label='m',plot_width=width, plot_height=height, tools = TOOLS)
    p.circle(x='l',y='m', size='snr', line_width = 1, color = 'colors', fill_alpha=0.3, source = source) # linewidth=0,
#p.circle(x=df.l,y=df.m, size=5, line_width = 1, color = cluster_colors, fill_alpha=0.5) # linewidth=0,
    hover = p.select(dict(type=HoverTool))
    hover.tooltips = [("m", "@m"), ("l", "@l"), ("time", "@time"), ("DM", "@dm"), ("SNR", "@snr")]

#p.circle(x,y, size=5, line_width = 1, color = colors)#, , fill_alpha=1) # linewidth=0,
#p.circle(x="x", y="y", source=source, size=7, color="color", line_color=None, fill_alpha="alpha")
    p2 = figure(title="DM vs time", x_axis_label='time', y_axis_label='DM',plot_width=width, plot_height=height, tools = TOOLS)
    p2.circle(x='time',y='dm', size='snr', line_width = 1, color = 'colors', fill_alpha=0.3, source=source) # linewidth=0,
    hover = p2.select(dict(type=HoverTool))
    hover.tooltips = [("m", "@m"), ("l", "@l"), ("time", "@time"), ("DM", "@dm"), ("SNR", "@snr")]

    p3 = figure(title="DM vs l", x_axis_label='l', y_axis_label='DM',plot_width=width, plot_height=height, tools = TOOLS)
    p3.circle(x='l',y='dm', size='snr', line_width = 1, color = 'colors', fill_alpha=0.3, source=source) # linewidth=0,
    hover = p3.select(dict(type=HoverTool))
    hover.tooltips = [("m", "@m"), ("l", "@l"), ("time", "@time"), ("DM", "@dm"), ("SNR", "@snr")]

    p4 = figure(title="time vs l", x_axis_label='l', y_axis_label='time',plot_width=width, plot_height=height, tools = TOOLS)
    p4.circle(x='l',y='time', size='snr', line_width = 1, color = 'colors', fill_alpha=0.3, source=source) # linewidth=0,
    hover = p4.select(dict(type=HoverTool))
    hover.tooltips = [("m", "@m"), ("l", "@l"), ("time", "@time"), ("DM", "@dm"), ("SNR", "@snr")]


# show the results
    show(column(row(p, p2), row(p3, p4)))


def makesummaryplot(candsfile):
    """ Given a scan's candsfile, read all candcollections and create
    bokeh summary plot
    TODO: modify to take candcollection
    """

    time = []
    segment = []
    integration = []
    dmind = []
    dtind = []
    snr = []
    dm = []
    dt = []
    l1 = []
    m1 = []
    for cc in iter_cands(candsfile):
        time.append(cc.candmjd*(24*3600))
        segment.append(cc.array['segment'])
        integration.append(cc.array['integration'])
        dmind.append(cc.array['dmind'])
        dtind.append(cc.array['dtind'])
        snr.append(cc.snrtot)
        dm.append(cc.canddm)
        dt.append(cc.canddt)
        l1.append(cc.array['l1'])
        m1.append(cc.array['m1'])

    time = np.concatenate(time)
#    time = time - time.min()  # TODO: try this, or ensure nonzero time array
    segment = np.concatenate(segment)
    integration = np.concatenate(integration)
    dmind = np.concatenate(dmind)
    dtind = np.concatenate(dtind)
    snr = np.concatenate(snr)
    dm = np.concatenate(dm)
    dt = np.concatenate(dt)
    l1 = np.concatenate(l1)
    m1 = np.concatenate(m1)

    keys = ['seg{0}-i{1}-dm{2}-dt{3}'.format(segment[i], integration[i],
                                             dmind[i], dtind[i])
            for i in range(len(segment))]
    sizes = calcsize(snr)
    colors = colorsat(l1, m1)
    data = dict(snrs=snr, dm=dm, l1=l1, m1=m1, time=time, sizes=sizes,
                colors=colors, keys=keys)

    dmt = plotdmt(data, yrange=(min(cc.state.dmarr), max(cc.state.dmarr)))
    loc = plotloc(data, extent=radians(cc.state.fieldsize_deg))
    combined = Row(dmt, loc, width=950)

    htmlfile = candsfile.replace('.pkl', '.html')
    output_file(htmlfile)
    save(combined)
    logger.info("Saved summary plot {0} with {1} candidate{2}"
                .format(htmlfile, len(segment), 's'[not len(segment)-1:]))

    return len(cc)


def plotdmt(data, circleinds=[], crossinds=[], edgeinds=[],
            tools="hover,pan,box_select,wheel_zoom,reset", plot_width=450,
            plot_height=400, yrange=None):
    """ Make a light-weight dm-time figure """

    fields = ['dm', 'time', 'sizes', 'colors', 'snrs', 'keys']

    if not len(circleinds):
        circleinds = list(range(len(data['snrs'])))

    # set ranges
    inds = circleinds + crossinds + edgeinds
    dm = [data['dm'][i] for i in inds]
    if yrange is None:
        dm_min = min(min(dm), max(dm)/1.2)
        dm_max = max(max(dm), min(dm)*1.2)
    else:
        assert isinstance(yrange, tuple)
        dm_min, dm_max = yrange
    time = [data['time'][i] for i in inds]
    time_min = min(time)*0.95
    time_max = max(time)*1.05

    source = ColumnDataSource(data=dict({(key, tuple([value[i] for i in circleinds if i not in edgeinds]))
                                        for (key, value) in list(data.items())
                                        if key in fields}))
    dmt = Figure(plot_width=plot_width, plot_height=plot_height,
                 toolbar_location="left", x_axis_label='Time (s; relative)',
                 y_axis_label='DM (pc/cm3)', x_range=(time_min, time_max),
                 y_range=(dm_min, dm_max),
                 output_backend='webgl', tools=tools)
    dmt.circle('time', 'dm', size='sizes', fill_color='colors',
               line_color=None, fill_alpha=0.2, source=source)

#    if crossinds:
#        sourceneg = ColumnDataSource(data = dict({(key, tuple([value[i] for i in crossinds]))
#                                                  for (key, value) in list(data.items()) if key in fields}))
#        dmt.cross('time', 'dm', size='sizes', fill_color='colors',
#                  line_alpha=0.3, source=sourceneg)
#
#    if edgeinds:
#        sourceedge = ColumnDataSource(data=dict({(key, tuple([value[i] for i in edgeinds]))
#                                                   for (key, value) in list(data.items()) if key in fields}))
#        dmt.circle('time', 'dm', size='sizes', line_color='colors',
#                   fill_color='colors', line_alpha=0.5, fill_alpha=0.2,
#                   source=sourceedge)

    hover = dmt.select(dict(type=HoverTool))
    hover.tooltips = OrderedDict([('SNR', '@snrs'), ('keys', '@keys')])

    return dmt


def plotloc(data, circleinds=[], crossinds=[], edgeinds=[],
            tools="hover,pan,box_select,wheel_zoom,reset", plot_width=450,
            plot_height=400, extent=None):
    """
    Make a light-weight loc figure
    extent is half size of (square) lm plot.
    """

    fields = ['l1', 'm1', 'sizes', 'colors', 'snrs', 'keys']

    if not len(circleinds):
        circleinds = list(range(len(data['snrs'])))

    # set ranges
    inds = circleinds + crossinds + edgeinds
    l1 = [data['l1'][i] for i in inds]
    m1 = [data['m1'][i] for i in inds]
    if extent is None:
        extent = max([max(m1), -min(m1), max(l1), -min(l1)])

    source = ColumnDataSource(data=dict({(key, tuple([value[i] for i in circleinds if i not in edgeinds]))
                                        for (key, value) in list(data.items())
                                        if key in fields}))
    loc = Figure(plot_width=plot_width, plot_height=plot_height,
                 toolbar_location="left", x_axis_label='l1 (rad)',
                 y_axis_label='m1 (rad)', x_range=(-extent, extent),
                 y_range=(-extent, extent),
                 output_backend='webgl', tools=tools)
    loc.circle('l1', 'm1', size='sizes', fill_color='colors',
               line_color=None, fill_alpha=0.2, source=source)

    hover = loc.select(dict(type=HoverTool))
    hover.tooltips = OrderedDict([('SNR', '@snrs'), ('keys', '@keys')])

    return loc


def calcsize(values, sizerange=(4, 70), inds=None, plaw=2):
    """ Use set of values to calculate symbol size.

    values is a list of floats for candidate significance.
    inds is an optional list of indexes to use to calculate symbol size.
    Scaling of symbol size min max set by sizerange tuple (min, max).
    plaw is powerlaw scaling of symbol size from values
    """

    if inds:
        smax = max([abs(values[i]) for i in inds])
        smin = min([abs(values[i]) for i in inds])
    else:
        smax = max([abs(val) for val in values])
        smin = min([abs(val) for val in values])

    if smax == smin:
        return [sizerange[1]]*len(values)
    else:
        return [sizerange[0] + sizerange[1] * ((abs(val) - smin)/(smax - smin))**plaw for val in values]


def colorsat(l, m):
    """ Returns color for given l,m
    Designed to look like a color wheel that is more saturated in middle.
    """

    lm = np.zeros(len(l), dtype='complex')
    lm.real = l
    lm.imag = m
    red = 0.5*(1+np.cos(np.angle(lm)))
    green = 0.5*(1+np.cos(np.angle(lm) + 2*3.14/3))
    blue = 0.5*(1+np.cos(np.angle(lm) - 2*3.14/3))
    amp = np.where(lm == 0, 256, 256*np.abs(lm)/np.abs(lm).max())
    return ["#%02x%02x%02x" % (np.floor(amp[i]*red[i]).astype(int),
            np.floor(amp[i]*green[i]).astype(int),
            np.floor(amp[i]*blue[i]).astype(int))
            for i in range(len(l))]


def calcinds(data, threshold, ignoret=None):
    """ Find indexes for data above (or below) given threshold. """

    inds = []
    for i in range(len(data['time'])):
        snr = data['snrs'][i]
        time = data['time'][i]
        if (threshold >= 0 and snr > threshold):
            if ignoret:
                incl = [t0 for (t0, t1) in ignoret if np.round(time).astype(int) in range(t0,t1)]
                logger.debug('{} {} {} {}'.format(np.round(time).astype(int), t0, t1, incl))
                if not incl:
                    inds.append(i)
            else:
                inds.append(i)
        elif threshold < 0 and snr < threshold:
            if ignoret:
                incl = [t0 for (t0, t1) in ignoret if np.round(time).astype(int) in range(t0,t1)]
                logger.debug('{} {} {} {}'.format(np.round(time).astype(int), t0, t1, incl))
                if not incl:
                    inds.append(i)
            else:
                inds.append(i)

    return inds


def candplot(canddatalist, snrs=None, cluster=None, outname=''):
    """ Takes output of search_thresh (CandData objects) to make
    candidate plots.
    Expects pipeline state, candidate location, image, and
    phased, dedispersed data (cut out in time, dual-pol).

    snrs is array for an (optional) SNR histogram plot.
    cluster allows cluster info to be passed in as (cluster_label, size).
    Written by Bridget Andersen and modified by Casey for rfpipe.
    """

    if not isinstance(canddatalist, list):
        logger.debug('Wrapping solo CandData object')
        canddatalist = [canddatalist]

    logger.info('Making {0} candidate plots.'.format(len(canddatalist)))

    for i in range(len(canddatalist)):
        canddata = canddatalist[i]
        st = canddata.state
        candloc = canddata.loc
        im = canddata.image
        data = canddata.data

        scan = st.metadata.scan
        segment, candint, dmind, dtind, beamnum = candloc

        # calc source location
#        imstd = util.madtostd(im)  # outlier resistant
        imstd = im.std()  # consistent with rfgpu
        snrim = im.max()/imstd
        l1, m1 = st.pixtolm(np.where(im == im.max()))

        logger.info('Plotting candloc {0} with SNR {1:.1f} and image/data shapes: {2}/{3}'
                    .format(str(candloc), snrim, str(im.shape), str(data.shape)))

        pt_ra, pt_dec = st.metadata.radec
        src_ra, src_dec = source_location(pt_ra, pt_dec, l1, m1)
        logger.info('Peak (RA, Dec): ({0}, {1})'.format(src_ra, src_dec))

        # convert l1 and m1 from radians to arcminutes
        l1arcm = np.degrees(l1)*60
        m1arcm = np.degrees(m1)*60

        # build overall plot
        fig = plt.Figure(figsize=(12.75, 8))

        # add metadata in subfigure
        ax = fig.add_subplot(2, 3, 1, facecolor='white')

        # calculate the overall dispersion delay: dd
        f1 = st.metadata.freq_orig[0]
        f2 = st.metadata.freq_orig[-1]
        dd = 4.15*st.dmarr[dmind]*(f1**(-2)-f2**(-2))

        # add annotating info
        # set spacing and location of the annotating information
        start = 1.1
        space = 0.07
        left = 0.0
        ax.text(left, start, st.fileroot, fontname='sans-serif',
                transform=ax.transAxes, fontsize='small')
        ax.text(left, start-space, 'Peak (arcmin): ('
                + str(np.round(l1arcm, 3)) + ', '
                + str(np.round(m1arcm, 3)) + ')',
                fontname='sans-serif', transform=ax.transAxes,
                fontsize='small')
        # split the RA and Dec and display in a nice format
        ra = src_ra.split()
        dec = src_dec.split()
        ax.text(left, start-2*space, 'Peak (RA, Dec): (' + ra[0] + ':' + ra[1]
                + ':' + ra[2][0:4] + ', ' + dec[0] + ':' + dec[1] + ':'
                + dec[2][0:4] + ')',
                fontname='sans-serif', transform=ax.transAxes,
                fontsize='small')
        ax.text(left, start-3*space, 'Source: ' + str(st.metadata.source),
                fontname='sans-serif', transform=ax.transAxes,
                fontsize='small')
        ax.text(left, start-4*space, 'scan: ' + str(scan),
                fontname='sans-serif', transform=ax.transAxes,
                fontsize='small')
        ax.text(left, start-5*space, 'segment: ' + str(segment),
                fontname='sans-serif', transform=ax.transAxes,
                fontsize='small')
        ax.text(left, start-6*space, 'integration: ' + str(candint),
                fontname='sans-serif', transform=ax.transAxes,
                fontsize='small')
        ax.text(left, start-7*space, 'DM = ' + str(st.dmarr[dmind])
                + ' (index ' + str(dmind) + ')',
                fontname='sans-serif', transform=ax.transAxes,
                fontsize='small')
        ax.text(left, start-8*space, 'dt = '
                + str(np.round(st.inttime*st.dtarr[dtind], 3)*1e3)
                + ' ms' + ' (index ' + str(dtind) + ')',
                fontname='sans-serif', transform=ax.transAxes,
                fontsize='small')
        ax.text(left, start-9*space, 'disp delay = ' + str(np.round(dd, 1))
                + ' ms',
                fontname='sans-serif', transform=ax.transAxes,
                fontsize='small')
        defstr = 'SNR (im'
        snrstr = str(np.round(snrim, 1))
        if canddata.snrk is not None:
            defstr += '/k): '
            snrstr += '/' + str(np.round(canddata.snrk, 1))
        else:
            defstr += '): '
        ax.text(left, start-10*space, defstr+snrstr,
                fontname='sans-serif', transform=ax.transAxes,
                fontsize='small')

        if cluster is not None:
            label, size = cluster
            ax.text(left, start-11*space, 'Cluster label: {0}'.format(str(label)),
                    fontname='sans-serif',
                    transform=ax.transAxes, fontsize='small')
            ax.text(left, start-12*space, 'Cluster size: {0}'.format(size),
                    fontname='sans-serif', transform=ax.transAxes,
                    fontsize='small')

        # set the plot invisible so that it doesn't interfere with annotations
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)
        ax.spines['bottom'].set_color('white')
        ax.spines['top'].set_color('white')
        ax.spines['right'].set_color('white')
        ax.spines['left'].set_color('white')

        # plot full dynamic spectra
        left, width = 0.75, 0.2*2./3.
        bottom, height = 0.2, 0.7
        # three rectangles for each panel of the spectrum (RR, RR+LL, LL)
        rect_dynsp1 = [left, bottom, width/3., height]
        rect_dynsp2 = [left+width/3., bottom, width/3., height]
        rect_dynsp3 = [left+2.*width/3., bottom, width/3., height]
        rect_lc1 = [left, bottom-0.1, width/3., 0.1]
        rect_lc2 = [left+width/3., bottom-0.1, width/3., 0.1]
        rect_lc3 = [left+2.*width/3., bottom-0.1, width/3., 0.1]
        rect_sp = [left+width, bottom, 0.1*2./3., height]
        ax_dynsp1 = fig.add_axes(rect_dynsp1)
        # sharey so that axes line up
        ax_dynsp2 = fig.add_axes(rect_dynsp2, sharey=ax_dynsp1)
        ax_dynsp3 = fig.add_axes(rect_dynsp3, sharey=ax_dynsp1)
        # hide RR+LL and LL dynamic spectra y labels to avoid overlap
        [label.set_visible(False) for label in ax_dynsp2.get_yticklabels()]
        [label.set_visible(False) for label in ax_dynsp3.get_yticklabels()]
        ax_sp = fig.add_axes(rect_sp, sharey=ax_dynsp3)
        [label.set_visible(False) for label in ax_sp.get_yticklabels()]
        ax_lc1 = fig.add_axes(rect_lc1)
        ax_lc2 = fig.add_axes(rect_lc2, sharey=ax_lc1)
        ax_lc3 = fig.add_axes(rect_lc3, sharey=ax_lc1)
        [label.set_visible(False) for label in ax_lc2.get_yticklabels()]
        [label.set_visible(False) for label in ax_lc3.get_yticklabels()]

        # now actually plot the data
        spectra = np.swapaxes(data.real, 0, 1)
        dd1 = spectra[..., 0]
        dd2 = spectra[..., 0] + spectra[..., 1]
        dd3 = spectra[..., 1]
        colormap = 'viridis'
        logger.debug('{0}'.format(dd1.shape))
        logger.debug('{0}'.format(dd2.shape))
        logger.debug('{0}'.format(dd3.shape))
        _ = ax_dynsp1.imshow(dd1, origin='lower', interpolation='nearest',
                             aspect='auto', cmap=plt.get_cmap(colormap))
        _ = ax_dynsp2.imshow(dd2, origin='lower', interpolation='nearest',
                             aspect='auto', cmap=plt.get_cmap(colormap))
        _ = ax_dynsp3.imshow(dd3, origin='lower', interpolation='nearest',
                             aspect='auto', cmap=plt.get_cmap(colormap))
        ax_dynsp1.set_yticks(list(range(0, len(st.freq), 30)))
        ax_dynsp1.set_yticklabels(st.freq[::30])
        ax_dynsp1.set_ylabel('Freq (GHz)')
        ax_dynsp1.set_xlabel('RR')
        ax_dynsp1.xaxis.set_label_position('top')
        ax_dynsp2.set_xlabel('RR+LL')
        ax_dynsp2.xaxis.set_label_position('top')
        ax_dynsp3.set_xlabel('LL')
        ax_dynsp3.xaxis.set_label_position('top')
        # hide xlabels invisible so that they don't interefere with lc plots
        [label.set_visible(False) for label in ax_dynsp1.get_xticklabels()]
        # This one y label was getting in the way
        ax_dynsp1.get_yticklabels()[0].set_visible(False)
        # plot stokes I spectrum of the candidate pulse (assume middle bin)
        # select stokes I middle bin
        spectrum = spectra[:, canddata.integration_rel].mean(axis=1)
        ax_sp.plot(spectrum, list(range(len(spectrum))), 'k.')
        # plot 0 Jy dotted line
        ax_sp.plot(np.zeros(len(spectrum)), list(range(len(spectrum))), 'r:')
        xmin, xmax = ax_sp.get_xlim()
        ax_sp.set_xticks(np.linspace(xmin, xmax, 3).round(2))
        ax_sp.set_xlabel('Flux (Jy)')

        # plot mean flux values for each time bin
        lc1 = dd1.mean(axis=0)
        lc2 = dd2.mean(axis=0)
        lc3 = dd3.mean(axis=0)
        lenlc = len(data)
        ax_lc1.plot(list(range(0, lenlc)), list(lc1)[:lenlc], 'k.')
        ax_lc2.plot(list(range(0, lenlc)), list(lc2)[:lenlc], 'k.')
        ax_lc3.plot(list(range(0, lenlc)), list(lc3)[:lenlc], 'k.')
        # plot 0 Jy dotted line for each plot
        ax_lc1.plot(list(range(0, lenlc)), list(np.zeros(lenlc)), 'r:')
        ax_lc2.plot(list(range(0, lenlc)), list(np.zeros(lenlc)), 'r:')
        ax_lc3.plot(list(range(0, lenlc)), list(np.zeros(lenlc)), 'r:')
        ax_lc2.set_xlabel('Integration (rel)')
        ax_lc1.set_ylabel('Flux (Jy)')
        ax_lc1.set_xticks([0, 0.5*lenlc, lenlc])
        # only show the '0' label for one of the plots to avoid messy overlap
        ax_lc1.set_xticklabels(['0', str(lenlc//2), str(lenlc)])
        ax_lc2.set_xticks([0, 0.5*lenlc, lenlc])
        ax_lc2.set_xticklabels(['', str(lenlc//2), str(lenlc)])
        ax_lc3.set_xticks([0, 0.5*lenlc, lenlc])
        ax_lc3.set_xticklabels(['', str(lenlc//2), str(lenlc)])
        ymin, ymax = ax_lc1.get_ylim()
        ax_lc1.set_yticks(np.linspace(ymin, ymax, 3).round(2))

        # adjust the x tick marks to line up with the lc plots
        ax_dynsp1.set_xticks([0, 0.5*lenlc, lenlc])
        ax_dynsp2.set_xticks([0, 0.5*lenlc, lenlc])
        ax_dynsp3.set_xticks([0, 0.5*lenlc, lenlc])

        # plot second set of dynamic spectra
        left, width = 0.45, 0.1333
        bottom, height = 0.1, 0.4
        rect_dynsp1 = [left, bottom, width/3., height]
        rect_dynsp2 = [left+width/3., bottom, width/3., height]
        rect_dynsp3 = [left+2.*width/3., bottom, width/3., height]
        rect_sp = [left+width, bottom, 0.1*2./3., height]
        ax_dynsp1 = fig.add_axes(rect_dynsp1)
        ax_dynsp2 = fig.add_axes(rect_dynsp2, sharey=ax_dynsp1)
        ax_dynsp3 = fig.add_axes(rect_dynsp3, sharey=ax_dynsp1)
        # hide RR+LL and LL dynamic spectra y labels
        [label.set_visible(False) for label in ax_dynsp2.get_yticklabels()]
        [label.set_visible(False) for label in ax_dynsp3.get_yticklabels()]
        ax_sp = fig.add_axes(rect_sp, sharey=ax_dynsp3)
        [label.set_visible(False) for label in ax_sp.get_yticklabels()]

        # calculate the channels to average together for SNR=2
        n = int((2.*(len(spectra))**0.5/snrim)**2)
        if n == 0:  # if n==0 then don't average
            dd1avg = dd1
            dd3avg = dd3
        else:
            # otherwise, add zeros onto the data so that it's length is cleanly
            # divisible by n (makes it easier to average over)
            dd1zerotemp = np.concatenate((np.zeros((n-len(spectra) % n,
                                                    len(spectra[0])),
                                         dtype=dd1.dtype), dd1), axis=0)
            dd3zerotemp = np.concatenate((np.zeros((n-len(spectra) % n,
                                                    len(spectra[0])),
                                         dtype=dd3.dtype), dd3), axis=0)
            # make masked arrays so appended zeros do not affect average
            zeros = np.zeros((len(dd1), len(dd1[0])))
            ones = np.ones((n-len(spectra) % n, len(dd1[0])))
            masktemp = np.concatenate((ones, zeros), axis=0)
            dd1zero = np.ma.masked_array(dd1zerotemp, mask=masktemp)
            dd3zero = np.ma.masked_array(dd3zerotemp, mask=masktemp)
            # average together the data
            dd1avg = np.array([], dtype=dd1.dtype)
            for i in range(len(spectra[0])):
                temp = dd1zero[:, i].reshape(-1, n)
                tempavg = np.reshape(np.mean(temp, axis=1), (len(temp), 1))
                # repeats the mean values to create more pixels
                # (easier to properly crop when it is finally displayed)
                temprep = np.repeat(tempavg, n, axis=0)
                if i == 0:
                    dd1avg = temprep
                else:
                    dd1avg = np.concatenate((dd1avg, temprep), axis=1)
            dd3avg = np.array([], dtype=dd3.dtype)
            for i in range(len(spectra[0])):
                temp = dd3zero[:, i].reshape(-1, n)
                tempavg = np.reshape(np.mean(temp, axis=1), (len(temp), 1))
                temprep = np.repeat(tempavg, n, axis=0)
                if i == 0:
                    dd3avg = temprep
                else:
                    dd3avg = np.concatenate((dd3avg, temprep), axis=1)
        dd2avg = dd1avg + dd3avg  # add together to get averaged RR+LL spectrum
        colormap = 'viridis'
        # if n==0 then don't crop the spectra because no zeroes were appended
        if n == 0:
            dd1avgcrop = dd1avg
            dd2avgcrop = dd2avg
            dd3avgcrop = dd3avg
        else:  # otherwise, crop off the appended zeroes
            dd1avgcrop = dd1avg[len(ones):len(dd1avg), :]
            dd2avgcrop = dd2avg[len(ones):len(dd2avg), :]
            dd3avgcrop = dd3avg[len(ones):len(dd3avg), :]
        logger.debug('{0}'.format(dd1avgcrop.shape))
        logger.debug('{0}'.format(dd2avgcrop.shape))
        logger.debug('{0}'.format(dd3avgcrop.shape))
        _ = ax_dynsp1.imshow(dd1avgcrop, origin='lower',
                             interpolation='nearest', aspect='auto',
                             cmap=plt.get_cmap(colormap))
        _ = ax_dynsp2.imshow(dd2avgcrop, origin='lower',
                             interpolation='nearest', aspect='auto',
                             cmap=plt.get_cmap(colormap))
        _ = ax_dynsp3.imshow(dd3avgcrop, origin='lower',
                             interpolation='nearest', aspect='auto',
                             cmap=plt.get_cmap(colormap))
        ax_dynsp1.set_yticks(list(range(0, len(st.freq), 30)))
        ax_dynsp1.set_yticklabels(st.freq[::30])
        ax_dynsp1.set_ylabel('Freq (GHz)')
        ax_dynsp1.set_xlabel('RR')
        ax_dynsp1.xaxis.set_label_position('top')
        ax_dynsp2.set_xlabel('Integration (rel)')
        ax2 = ax_dynsp2.twiny()
        ax2.set_xlabel('RR+LL')
        [label.set_visible(False) for label in ax2.get_xticklabels()]
        ax_dynsp3.set_xlabel('LL')
        ax_dynsp3.xaxis.set_label_position('top')

        # plot stokes I spectrum of the candidate pulse from middle integration
        ax_sp.plot(dd2avgcrop[:, canddata.integration_rel]/2.,
                   list(range(len(dd2avgcrop))), 'k.')
        ax_sp.plot(np.zeros(len(dd2avgcrop)), list(range(len(dd2avgcrop))),
                   'r:')
        xmin, xmax = ax_sp.get_xlim()
        ax_sp.set_xticks(np.linspace(xmin, xmax, 3).round(2))
        ax_sp.get_xticklabels()[0].set_visible(False)
        ax_sp.set_xlabel('Flux (Jy)')

        # readjust the x tick marks on the dynamic spectra
        ax_dynsp1.set_xticks([0, 0.5*lenlc, lenlc])
        ax_dynsp1.set_xticklabels(['0', str(lenlc//2), str(lenlc)])
        ax_dynsp2.set_xticks([0, 0.5*lenlc, lenlc])
        ax_dynsp2.set_xticklabels(['', str(lenlc//2), str(lenlc)])
        ax_dynsp3.set_xticks([0, 0.5*lenlc, lenlc])
        ax_dynsp3.set_xticklabels(['', str(lenlc//2), str(lenlc)])

        # plot the image and zoomed cutout
        ax = fig.add_subplot(2, 3, 4)
        fov = np.degrees(1./st.uvres)*60.
        _ = ax.imshow(im.transpose(), aspect='equal', origin='upper',
                      interpolation='nearest',
                      extent=[fov/2, -fov/2, -fov/2, fov/2],
                      cmap=plt.get_cmap('viridis'), vmin=0,
                      vmax=0.5*im.max())
        ax.set_xlabel('RA Offset (arcmin)')
        ax.set_ylabel('Dec Offset (arcmin)')
        # to set scale when we plot the triangles that label the location
        ax.autoscale(False)
        # add markers on the axes at measured position of the candidate
        ax.scatter(x=[l1arcm], y=[-fov/2], c='#ffff00', s=60, marker='^',
                   clip_on=False)
        ax.scatter(x=[fov/2], y=[m1arcm], c='#ffff00', s=60, marker='>',
                   clip_on=False)
        # makes it so the axis does not intersect the location triangles
        ax.set_frame_on(False)

        # add a zoomed cutout image of the candidate (set width at 5*beam)
        sbeam = np.mean(st.beamsize_deg)*60
        # figure out the location to center the zoomed image on
        xratio = len(im[0])/fov  # pix/arcmin
        yratio = len(im)/fov  # pix/arcmin
        mult = 5  # sets how many times the synthesized beam the zoomed FOV is
        xmin = max(0, int(len(im[0])//2-(m1arcm+sbeam*mult)*xratio))
        xmax = int(len(im[0])//2-(m1arcm-sbeam*mult)*xratio)
        ymin = max(0, int(len(im)//2-(l1arcm+sbeam*mult)*yratio))
        ymax = int(len(im)//2-(l1arcm-sbeam*mult)*yratio)
        left, width = 0.231, 0.15
        bottom, height = 0.465, 0.15
        rect_imcrop = [left, bottom, width, height]
        ax_imcrop = fig.add_axes(rect_imcrop)
        logger.debug('{0}'.format(im.transpose()[xmin:xmax, ymin:ymax].shape))
        logger.debug('{0} {1} {2} {3}'.format(xmin, xmax, ymin, ymax))
        _ = ax_imcrop.imshow(im.transpose()[xmin:xmax,ymin:ymax], aspect=1,
                             origin='upper', interpolation='nearest',
                             extent=[-1, 1, -1, 1],
                             cmap=plt.get_cmap('viridis'), vmin=0,
                             vmax=0.5*im.max())
        # setup the axes
        ax_imcrop.set_ylabel('Dec (arcmin)')
        ax_imcrop.set_xlabel('RA (arcmin)')
        ax_imcrop.xaxis.set_label_position('top')
        ax_imcrop.xaxis.tick_top()
        xlabels = [str(np.round(l1arcm+sbeam*mult/2, 1)), '',
                   str(np.round(l1arcm, 1)), '',
                   str(np.round(l1arcm-sbeam*mult/2, 1))]
        ylabels = [str(np.round(m1arcm-sbeam*mult/2, 1)), '',
                   str(np.round(m1arcm, 1)), '',
                   str(np.round(m1arcm+sbeam*mult/2, 1))]
        ax_imcrop.set_xticklabels(xlabels)
        ax_imcrop.set_yticklabels(ylabels)
        # change axis label loc of inset to avoid the full picture
        ax_imcrop.get_yticklabels()[0].set_verticalalignment('bottom')

        # create SNR versus N histogram for the whole observation
        # (properties for each candidate in the observation given by prop)
        if snrs is not None:
            left, width = 0.45, 0.2
            bottom, height = 0.6, 0.3
            rect_snr = [left, bottom, width, height]
            ax_snr = fig.add_axes(rect_snr)
            pos_snrs = snrs[snrs >= 0]
            neg_snrs = snrs[snrs < 0]
            if not len(neg_snrs):  # if working with subset and only pos snrs
                neg_snrs = pos_snrs
                nonegs = True
            else:
                nonegs = False
            minval = 5.5
            maxval = 8.0
            # determine the min and max values of the x axis
            if min(pos_snrs) < min(np.abs(neg_snrs)):
                minval = min(pos_snrs)
            else:
                minval = min(np.abs(neg_snrs))
            if max(pos_snrs) > max(np.abs(neg_snrs)):
                maxval = max(pos_snrs)
            else:
                maxval = max(np.abs(neg_snrs))

            # positive SNR bins are in blue
            # absolute values of negative SNR bins are taken and plotted as
            # red x's on top of positive blue bins for compactness
            n, b, patches = ax_snr.hist(pos_snrs, 50, (minval, maxval),
                                        facecolor='blue', zorder=1)
            vals, bin_edges = np.histogram(np.abs(neg_snrs), 50,
                                           (minval, maxval))
            bins = np.array([(bin_edges[i]+bin_edges[i+1])/2.
                             for i in range(len(vals))])
            vals = np.array(vals)
            if not nonegs:
                ax_snr.scatter(bins[vals > 0], vals[vals > 0], marker='x',
                               c='orangered', alpha=1.0, zorder=2)
            ax_snr.set_xlabel('SNR')
            ax_snr.set_xlim(left=minval-0.2)
            ax_snr.set_xlim(right=maxval+0.2)
            ax_snr.set_ylabel('N')
            ax_snr.set_yscale('log')
            # draw vertical line where the candidate SNR is
            ax_snr.axvline(x=snrim, linewidth=1, color='y', alpha=0.7)

        if not outname:
            outname = os.path.join(st.prefs.workdir,
                                   'cands_{0}_seg{1}-i{2}-dm{3}-dt{4}.png'
                                   .format(st.fileroot, segment, candint,
                                           dmind, dtind))

        try:
            canvas = FigureCanvasAgg(fig)
            canvas.print_figure(outname)
            logger.info('Wrote candidate plot to {0}'.format(outname))
        except ValueError:
            logger.warn('Could not write figure to {0}'.format(outname))


def source_location(pt_ra, pt_dec, l1, m1):
    """ Takes phase center and src l,m in radians to get ra,dec of source.
    Returns string ('hh mm ss', 'dd mm ss')
    """

    srcra = np.degrees(pt_ra + l1/cos(pt_dec))
    srcdec = np.degrees(pt_dec + m1)

    return deg2HMS(srcra, srcdec)


def deg2HMS(ra=None, dec=None, round=False):
    """ quick and dirty coord conversion. googled to find bdnyc.org.
    """
    RA, DEC, rs, ds = '', '', '', ''
    if dec is not None:
        if str(dec)[0] == '-':
            ds, dec = '-', abs(dec)
        deg = int(dec)
        decM = abs(int((dec-deg)*60))
        if round:
            decS = int((abs((dec-deg)*60)-decM)*60)
        else:
            decS = (abs((dec-deg)*60)-decM)*60
        DEC = '{0}{1} {2} {3}'.format(ds, deg, decM, decS)

    if ra is not None:
        if str(ra)[0] == '-':
            rs, ra = '-', abs(ra)
        raH = int(ra/15)
        raM = int(((ra/15)-raH)*60)
        if round:
            raS = int(((((ra/15)-raH)*60)-raM)*60)
        else:
            raS = ((((ra/15)-raH)*60)-raM)*60
        RA = '{0}{1} {2} {3}'.format(rs, raH, raM, raS)

    if ra is not None and dec is not None:
        return (RA, DEC)
    else:
        return RA or DEC
