from __future__ import unicode_literals

import copy
import matplotlib as mpl
mpl.use('Agg')
mpl.rcParams['svg.fonttype'] = 'none'
import matplotlib.pyplot as plt
import math
from scipy.interpolate import interp1d
import os
import glob
import sys
import csv
import numpy
import operator
import itertools

import utils
import plotconfig
from hist import Hist
import treeutils

#                   green    dark red  light blue  light red  sky blue  pink/purple   grey
default_colors = ['#006600', '#990012', '#2b65ec', '#cc0000', '#3399ff', '#a821c7', '#808080']
default_linewidths = ['5', '3', '2', '2', '2']
pltcolors = plt.rcParams['axes.prop_cycle'].by_key()['color']  # pyplot/matplotlib default colors
frozen_pltcolors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']  # default colors from version 2.2.4 (so we don't get different colors on different machines/installs)

plot_ratios = {
    'v' : (30, 3),
    'd' : (8, 4),
    'j' : (8, 3)
}

# # ----------------------------------------------------------------------------------------
# def _hls2hex(rgb_tuple):
#     h, l, s, alpha = rgb_tuple
#     hexstr = '#%02x%02x%02x' %tuple(map(lambda x: int(x*255), colorsys.hls_to_rgb(h, l, s)))
#     print rgb_tuple, hexstr
#     return hexstr

# ----------------------------------------------------------------------------------------
def getgrey(gtype='medium'):
    if gtype == 'medium':
        return '#929292'
    elif gtype == 'light-medium':
        return '#cdcdcd'
    elif gtype == 'light':
        return '#d3d3d3'
    elif gtype == 'white':
        return '#ffffff'
    else:
        assert False

# ----------------------------------------------------------------------------------------
def rgb_to_hex(rgb_tuple):
    assert len(rgb_tuple) == 3
    return '#%02x%02x%02x' %tuple(map(lambda x: int(x*255), rgb_tuple[:3]))

# ----------------------------------------------------------------------------------------
def truncate_colormap(cmap, minval=0.0, maxval=1.0, n=100):
    new_cmap = mpl.colors.LinearSegmentedColormap.from_list(
        'trunc({n},{a:.2f},{b:.2f})'.format(n=cmap.name, a=minval, b=maxval),
        cmap(numpy.linspace(minval, maxval, n)))
    return new_cmap

# ----------------------------------------------------------------------------------------
def get_normalized_cmap_and_norm(vals, cmap=None, remove_top_end=False, hard_min=None):
    if cmap is None:
        cmap = plt.cm.Blues  # 'Blues'
    if len(vals) == 0:
        print '  %s zero values passed to get_normalized_cmap_and_norm' % utils.color('yellow', 'warning')
        vals = [0.]
    sorted_vals = sorted(vals)
    vmin = sorted_vals[0] - 0.2 * (sorted_vals[-1] - sorted_vals[0]) if hard_min is None else hard_min  # don't want anybody to be white, so set <vmin> to a bit less than the actual min value (i.e. so white corresponds to a value that's a bit less than any of our values)
    vmax = sorted_vals[-1]
    if remove_top_end:  # remove the top end of the color spectrum (at least when I'm adding this, it's because the Reds and Blues top color is way too close to black [and I can't set opacity on lines in ete3, which would also fix it])
        vmax = vmax + 0.3 * (vmax - vmin)
    norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)
    return cmap, norm

# ----------------------------------------------------------------------------------------
def get_normalized_scalar_map(vals, cmap=None, remove_top_end=False, hard_min=None):
    cmap, norm = get_normalized_cmap_and_norm(vals, cmap=cmap, remove_top_end=remove_top_end, hard_min=hard_min)
    scalarMap = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    return scalarMap

# ----------------------------------------------------------------------------------------
def get_smap_color(smap, info, key=None, val=None):  # specify *either* <key> or <val> (don't need <info> if you're passing <val>)
    if val is None:
        assert key is not None
        if key not in info or info[key] is None:
            return getgrey()
        val = info[key]
    rgb_code = smap.to_rgba(val)[:3]
    return rgb_to_hex(rgb_code)

# ----------------------------------------------------------------------------------------
def set_bins(values, n_bins, is_log_x, xbins, var_type='float'):
    """ NOTE <values> should be sorted """
    assert len(values) > 0
    values = sorted(values)
    if is_log_x:
        log_xmin = math.log(pow(10.0, math.floor(math.log10(values[0]))))  # round down to the nearest power of 10 from the first entry
        log_xmax = math.log(pow(10.0, math.ceil(math.log10(values[-1]))))  # round up to the nearest power of 10 from the last entry
        log_dx = (log_xmax - log_xmin) / float(n_bins)
        log_xmin -= 0.1*log_dx  # expand a little to avoid overflows
        log_xmax += 0.1*log_dx
        log_dx = (log_xmax - log_xmin) / float(n_bins)
        for ib in range(n_bins+1):
            low_edge = math.exp(log_xmin + ib*log_dx)
            xbins[ib] = low_edge
    else:
        dx, xmin, xmax = 0, 0, 0
        if var_type == 'string':
            xmin = 0.5
            xmax = n_bins + 0.5
        else:
            dx = float(values[-1] - values[0]) / n_bins
            if dx == 0:  # hackey, but effective
                dx = max(1e-5, values[0])
            xmin = values[0] - 0.1*dx  # expand a little to avoid underflows
            xmax = values[-1] + 0.1*dx  # and overflows
        dx = float(xmax - xmin) / n_bins  # then recalculate dx
        for ib in range(n_bins+1):
            xbins[ib] = xmin + ib*dx

# ----------------------------------------------------------------------------------------
def write_hist_to_file(fname, hist):
    """ see the make_hist_from* functions to reverse this operation """
    with open(fname, 'w') as histfile:
        writer = csv.DictWriter(histfile, ('bin_low_edge', 'contents', 'binerror', 'xtitle', 'binlabel'))  # this is a really crummy way of writing style information, but root files *suck*, so this is what I do for now
        writer.writeheader()
        for ibin in range(hist.GetNbinsX() + 2):
            writer.writerow({
                'bin_low_edge' : hist.GetXaxis().GetBinLowEdge(ibin),
                'contents' : hist.GetBinContent(ibin),
                'binerror' : hist.GetBinError(ibin),
                'xtitle' : hist.GetXaxis().GetTitle(),
                'binlabel' : hist.GetXaxis().GetBinLabel(ibin)
            })

# ----------------------------------------------------------------------------------------
def make_bool_hist(n_true, n_false, hist_label):
    """ fill a two-bin histogram with the fraction false in the first bin and the fraction true in the second """
    if 'fraction_uncertainty' not in sys.modules:
        import fraction_uncertainty

    hist = Hist(2, -0.5, 1.5, ytitle='freq')

    def set_bin(numer, denom, ibin, label):
        frac = float(numer) / denom
        bounds = sys.modules['fraction_uncertainty'].err(numer, denom)
        err = max(abs(frac - bounds[0]), abs(frac - bounds[1]))
        hist.set_ibin(ibin, frac, error=err, label=label)

    set_bin(n_true, n_true + n_false, 1, 'right')
    set_bin(n_false, n_true + n_false, 2, 'wrong')

    return hist

# ----------------------------------------------------------------------------------------
# <values> is of form {<bin 1>:<counts 1>, <bin 2>:<counts 2>, ...}
def make_hist_from_dict_of_counts(values, var_type, hist_label, log='', xmin_force=0.0, xmax_force=0.0, sort=False):
    """ Fill a histogram with values from a dictionary (each key will correspond to one bin) """
    assert var_type == 'int' or var_type == 'string'  # floats should be handled by Hist class in hist.py

    if len(values) == 0:
        print 'WARNING no values for %s in make_hist' % hist_label
        return Hist(1, 0, 1)

    bin_labels = sorted(values)
    if not sort and var_type == 'string':  # for strings, sort so most common value is to left side
        bin_labels = sorted(values, key=values.get, reverse=True)

    if var_type == 'string':
        n_bins = len(values)
    else:
        n_bins = bin_labels[-1] - bin_labels[0] + 1

    hist = None
    xbins = [0. for _ in range(n_bins+1)]  # NOTE the +1 is 'cause you need the lower edge of the overflow bin
    if xmin_force == xmax_force:  # if boundaries aren't set explicitly, work out what they should be
        if var_type == 'string':
            set_bins(bin_labels, n_bins, 'x' in log, xbins, var_type)
            hist = Hist(n_bins, xbins[0], xbins[-1], xbins=xbins)
        else:
            hist = Hist(n_bins, bin_labels[0] - 0.5, bin_labels[-1] + 0.5)  # for integers, just go from the first to the last bin label (they're sorted)
    else:
      hist = Hist(n_bins, xmin_force, xmax_force)

    for ival in range(len(values)):
        if var_type == 'string':
            label = bin_labels[ival]
            ibin = ival + 1
        else:
            label = ''
            ibin = hist.find_bin(bin_labels[ival])
        hist.set_ibin(ibin, values[bin_labels[ival]], error=math.sqrt(values[bin_labels[ival]]), label=label)
  
    # make sure there's no overflows
    if hist.bin_contents[0] != 0.0 or hist.bin_contents[-1] != 0.0:
        for ibin in range(hist.n_bins + 2):
            print '%d %f %f' % (ibin, hist.low_edges[ibin], hist.bin_contents[ibin])
        raise Exception('overflows in ' + hist_label)

    return hist

# ----------------------------------------------------------------------------------------
def add_bin_labels_not_in_all_hists(hists):
    """ find the OR of all bin labels present in <hists>, and remake each hist in <hists> to have zero bins for any that weren't there already """
    # first convert each hist to a map from bin label to entries
    all_labels = []
    histmaps = []
    for hist in hists:
        histmaps.append({})
        for ibin in range(1, hist.n_bins + 1):  # ignore under/over flows, they're kinda useless for bin-labelled hists
            label = hist.bin_labels[ibin]
            histmaps[-1][label] = (hist.bin_contents[ibin], hist.errors[ibin])  # 2-tuple with (content, error)
            if label not in all_labels:
                all_labels.append(label)

    all_labels = sorted(all_labels)

    # then go through and make new histograms for everybody
    finalhists = []
    for ih in range(len(histmaps)):
        original_hist = hists[ih]
        hmap = histmaps[ih]
        finalhists.append(Hist(len(all_labels), 0.5, len(all_labels) + 0.5, title=original_hist.title))
        for ilabel in range(len(all_labels)):
            label = all_labels[ilabel]
            ibin = ilabel + 1  # root conventions
            finalhists[-1].bin_labels[ibin] = label
            if label in hmap:
                finalhists[-1].bin_contents[ibin] = hmap[label][0]
                finalhists[-1].errors[ibin] = hmap[label][1]
            else:
                finalhists[-1].bin_contents[ibin] = 0.0
                finalhists[-1].errors[ibin] = 0.0

    return finalhists

# ----------------------------------------------------------------------------------------
def shift_hist_overflows(hists, xmin, xmax):
    for htmp in hists:
        if htmp is None:
            continue
        underflows, overflows = 0., 0.
        under_err2, over_err2 = 0., 0.  # sum of squared errors
        first_shown_bin, last_shown_bin = -1, -1
        bin_centers = htmp.get_bin_centers(ignore_overflows=False)
        for ib in range(0, htmp.n_bins + 2):
            if bin_centers[ib] <= xmin:
                underflows += htmp.bin_contents[ib]
                under_err2 += htmp.errors[ib]**2
                htmp.set_ibin(ib, 0., error=0.)
            elif first_shown_bin == -1:
                first_shown_bin = ib
            else:
                break
        for ib in reversed(range(0, htmp.n_bins + 2)):
            if bin_centers[ib] >= xmax:
                overflows += htmp.bin_contents[ib]
                over_err2 += htmp.errors[ib]**2
                htmp.set_ibin(ib, 0., error=0.)
            elif last_shown_bin == -1:
                last_shown_bin = ib
            else:
                break

        htmp.set_ibin(first_shown_bin,
                      underflows + htmp.bin_contents[first_shown_bin],
                      error=math.sqrt(under_err2 + htmp.errors[first_shown_bin]**2))
        htmp.set_ibin(last_shown_bin,
                      overflows + htmp.bin_contents[last_shown_bin],
                      error=math.sqrt(over_err2 + htmp.errors[last_shown_bin]**2))

# ----------------------------------------------------------------------------------------
def draw_no_root(hist, log='', plotdir=None, plotname='foop', more_hists=None, scale_errors=None, normalize=False, bounds=None,
                 figsize=None, shift_overflows=False, colors=None, errors=False, write_csv=False, xline=None, yline=None, xyline=None, linestyles=None,
                 linewidths=None, plottitle=None, csv_fname=None, stats='', print_stats=False, translegend=(0., 0.), rebin=None,
                 xtitle=None, ytitle=None, markersizes=None, no_labels=False, only_csv=False, alphas=None, remove_empty_bins=False,
                 square_bins=False):
    assert os.path.exists(plotdir)

    hists = [hist,]
    if more_hists is not None:
        hists = hists + more_hists

    xmin, xmax, ymin, ymax = None, None, None, None
    for htmp in hists:
        if htmp.title == 'null':  # empty hists
            continue
        if scale_errors is not None:
            factor = float(scale_errors[0]) if len(scale_errors) == 1 else float(scale_errors[hists.index(htmp)])
            for ibin in range(htmp.n_bins + 2):
                htmp.errors[ibin] *= factor
        if normalize:  # NOTE removed <normalization_bounds> option, hopefully I'm not using it any more
            htmp.normalize()
        if ymin is None or htmp.get_minimum(xbounds=bounds) < ymin:  # adding this afterwards, so might screw up something below
            ymin = htmp.get_minimum(xbounds=bounds, exclude_empty='y' in log)
        if ymax is None or htmp.get_maximum(xbounds=bounds) > ymax:
            ymax = htmp.get_maximum(xbounds=bounds)
        if xmin is None or htmp.xmin < xmin:  # overridden by <bounds> below
            xmin = htmp.xmin
        if xmax is None or htmp.xmax > xmax:
            xmax = htmp.xmax

    if bounds is not None:
        xmin, xmax = bounds

    if shift_overflows:
        if '_vs_per_gene_support' in plotname or '_fraction_correct_vs_mute_freq' in plotname or plotname in [r + '_gene' for r in utils.regions]:
            print '%s overriding overflow shifting for %s' % (utils.color('yellow', 'warning'), plotname)
        else:
            shift_hist_overflows(hists, xmin, xmax)
        # assert '_vs_per_gene_support' not in plotname and '_fraction_correct_vs_mute_freq' not in plotname and plotname.find('_gene') != 1  # really, really, really don't want to shift overflows for these

    if write_csv:
        assert more_hists is None  # can't write a superposition on multiple hists to a single csv
        if csv_fname is None:
            hist.write(plotdir + '/' + plotname + '.csv')
        else:
            hist.write(csv_fname)

    if only_csv:
        return

    # this is the slow part of plotting (well, writing the svg is also slow)
    fig, ax = mpl_init(figsize=figsize)
    mpl.rcParams.update({'legend.fontsize' : 15})

    tmpcolors = copy.deepcopy(colors)  # don't want to modify the arguments
    if tmpcolors is None:  # fiddle here http://stackoverflow.com/questions/22408237/named-colors-in-matplotlib
        tmpcolors = ['royalblue', 'darkred', 'green', 'darkorange']
    n_different_colors = len(tmpcolors)
    while len(tmpcolors) < len(hists):
        tmpcolors += tmpcolors

    tmplinestyles = [] if linestyles is None or len(linestyles) < len(hists) else copy.deepcopy(linestyles)
    itmp = 0
    availstyles = ['-', '--', '-.', ':']
    while len(tmplinestyles) < len(hists):
        tmplinestyles += [availstyles[itmp % len(availstyles)] for _ in range(n_different_colors)]
        itmp += 1

    def floatstr(val):
        ndig = 1 if val > 1 else 3
        return ('%.'+str(ndig)+'f') % val
    for ih in range(len(hists)):
        htmp = hists[ih]
        statstr = None
        if stats == 'mean':
            statstr = ' (mean %s)' % floatstr(htmp.get_mean())
        elif stats == 'absmean':
            statstr = ' (abs av %s)' % floatstr(htmp.get_mean(absval=True))
        elif stats == '0-bin':
            statstr = ' (%s %s)' % ('0-bin' if htmp.bin_labels[1]=='' else htmp.bin_labels[1], floatstr(htmp.bin_contents[1]))
        elif stats is not None and stats != '':  # damnit, I ended up with both of the damn things as possible defaults
            raise Exception('unexpected stats str \'%s\'' % stats)
        markersize = None
        if markersizes is not None:
            imark = ih if len(markersizes) > 1 else 0
            markersize = markersizes[imark]
        linewidth = None
        if linewidths is None:
            if ih < 6 and len(hists) > 1:
                linewidth = 6-ih
        else:
            ilw = ih if len(linewidths) > 1 and ih < len(linewidths) else 0
            linewidth = linewidths[ilw]
        if rebin is not None:
            htmp.rebin(rebin)
        alpha = 1.
        if alphas is not None:
            alpha = alphas[ih]
        # i'm not sure why the linewidths get to here as strings, I guess that used to work, but now it kicks this really opaque error TypeError: Cannot cast array data from dtype('<U1') to dtype('float64') according to the rule 'safe'
        htmp.mpl_plot(ax, color=tmpcolors[ih], linewidth=linewidth, linestyle=tmplinestyles[ih], ignore_overflows=True, errors=errors, alpha=alpha, markersize=markersize, remove_empty_bins=remove_empty_bins, square_bins=square_bins)

    # NOTE it would be nice to combine xline, yline, and xyline (I don't want to go find everwhere that calls this right now)
    if xline is not None:
        ax.plot([xline, xline], [-0.1*ymax, 0.5*ymax], color='black', linestyle='--', linewidth=3)
    if yline is not None:
        print '%s fix y line' % utils.color('red', 'error')
    if xyline is not None:
        assert len(xyline) == 2
        assert len(xyline[0]) == 2 and len(xyline[1]) == 2
        ax.plot([xyline[0][0], xyline[1][0]], [xyline[0][1], xyline[1][1]], color='black', linestyle='--', linewidth=3)
    # if yline is not None:
    #     # if yline < hframe.GetYaxis().GetXmin() or xline > hframe.GetYaxis().GetXmax():  # make sure we got valid a x position for the line
    #     #     print 'WARNING plotting y line at %f out of bounds (%f, %f)' % (float(ymin), hframe.GetYaxis().GetXmin(), hframe.GetYaxis().GetXmax())
    #     yl = TLine(hframe.GetXaxis().GetXmin(), yline, hframe.GetXaxis().GetXmax(), yline)
    #     yl.Draw()

    xticks, xticklabels = None, None
    if not no_labels and hist.bin_labels.count('') != len(hist.bin_labels):
        xticks = hist.get_bin_centers()
        xticklabels = hist.bin_labels

    if plottitle is not None:
        tmptitle = plottitle
    elif plotname in plotconfig.plot_titles:
        tmptitle = plotconfig.plot_titles[plotname]
    else:
        tmptitle = hist.title  # hm, maybe shouldn't be hist.title? I think that's usually supposed to be the legend
    if statstr is not None:
        tmptitle += statstr
        if print_stats:
            print '    %s %s' % (plotname, statstr)

    if xtitle is not None:
        tmpxtitle = xtitle
    elif plotname in plotconfig.xtitles:
        tmpxtitle = plotconfig.xtitles[plotname]
    else:
        tmpxtitle = hist.xtitle  # hm, maybe shouldn't be hist.title? I think that's usually supposed to be the legend

    ymin = 0.8 * ymin if 'y' in log else -0.03*ymax
    mpl_finish(ax, plotdir, plotname,
               title=tmptitle,
               xlabel=tmpxtitle,
               ylabel=hist.ytitle if ytitle is None else ytitle,
               xbounds=[xmin, xmax],
               ybounds=[ymin, 1.15*ymax],
               leg_loc=(0.72 + translegend[0], 0.7 + translegend[1]),
               log=log, xticks=xticks, xticklabels=xticklabels,
               no_legend=(len(hists) <= 1), adjust={'left' : 0.2})
    plt.close()

# ----------------------------------------------------------------------------------------
def get_unified_bin_hist(hists):
    """ 
    Unify bins in <hists>.
    Starts from the bins from <hists[0]>, then loops over the rest of 'em adding bins as it goes (with width from <hists[0]>) so we won't have any under/overflows.
    NOTE totally ignores under/overflows in the original hists. That's on purpose, but like everying else in this foolish thing we call life may in fact turn out to be dumb later on.
    """
    assert len(hists) > 0
    dx = hists[0].GetXaxis().GetBinLowEdge(2) - hists[0].GetXaxis().GetBinLowEdge(1)  # always have at least one bin, in which case this'd be the low edge of the overflow bin minus low edge of the first bin
    # print 'dx:', dx
    low_edges = []
    for ib in range(1, hists[0].GetNbinsX()+1):
        low_edges.append(hists[0].GetXaxis().GetBinLowEdge(ib))

    # for d in [ low_edges[i] - low_edges[i-1] for i in range(1, len(low_edges)) ]:
    #     print ' ', d

    for hist in hists[1:]:
        for ib in range(1, hist.GetNbinsX()+1):
            bincenter = hist.GetXaxis().GetBinCenter(ib)
            while bincenter <= low_edges[0]:  # as long as <bincenter> is outside of the current bounds, keep adding bins on the left...
                low_edges.insert(0, low_edges[0] - dx)
            while bincenter >= low_edges[-1] + dx:  # ...and same thing on the right
                low_edges.insert(len(low_edges), low_edges[-1] + dx)

    return Hist(len(low_edges), low_edges[0], low_edges[-1] + dx)

# ----------------------------------------------------------------------------------------
def get_cluster_size_hist(partition, rebin=None):
    sizes = [len(c) for c in partition]
    nbins = max(sizes)
    # if nbins > 30:
    #     rebin = 2
    if rebin is not None:
        nbins = int(float(nbins) / rebin)
    hist = Hist(nbins, 0.5, max(sizes) + 0.5, xtitle='cluster size', title='x')
    for sz in sizes:
        hist.fill(sz)
    return hist

# ----------------------------------------------------------------------------------------
def make_mean_hist(hists):
    """ return the hist with bin contents the mean over <hists> of each bin """
    binvals = {}
    for hist in hists:  # I could probably do this with list comprehensions or something, but this way handles different bin bounds
        for ib in range(0, hist.n_bins + 2):
            low_edge = hist.low_edges[ib]
            if low_edge not in binvals:
                binvals[low_edge] = []
            binvals[low_edge].append(hist.bin_contents[ib])
    binlist = sorted(binvals.keys())
    meanhist = Hist(len(binlist) - 2, binlist[1], binlist[-1], xbins=binlist[1 :])
    for ib in range(len(binlist)):
        vlist = binvals[binlist[ib]]
        meanhist.set_ibin(ib, numpy.mean(vlist), error=(numpy.std(vlist, ddof=1) / math.sqrt(len(vlist))))
    # meanhist.normalize()
    return meanhist

# ----------------------------------------------------------------------------------------
def interpolate_values(xvals, yvals):
    """ Replace any instances of None in <yvals> which have non-Non values on both sides with a linear interpolation """
    xvals_no_none, yvals_no_none = [], []
    for ip in range(len(yvals)):
        if yvals[ip] is not None:
            xvals_no_none.append(xvals[ip])
            yvals_no_none.append(yvals[ip])

    fcn = interp1d(xvals_no_none, yvals_no_none)
    for ip in range(len(yvals)):
        if yvals[ip] is None:
            try:
                yvals[ip] = int(fcn([xvals[ip], ])[0])
            except ValueError:
                pass

# ----------------------------------------------------------------------------------------
# NOTE annotation stuff is in plotconfig.py
#
legends = {'vollmers-0.9' : 'VJ CDR3 0.9',
           # 'partition partis' : 'full partis',
           'partition' : 'full partis',
           # 'naive-hamming-partition partis' : 'point partis',
           'naive-hamming-partition' : 'point partis',
           # 'vsearch-partition partis' : 'vsearch partis',
           'vsearch-partition' : 'vsearch partis',
           'seed-partition' : 'full partis (seed)',
           'seed-naive-hamming-partition' : 'point partis (seed)',
           'changeo' : 'IMGT + Change-O',
           # '0.1-true-singletons' : '10% random singletons',
           # '0.1-true-reassign' : '10% random reassign',
           'misassign-0.60-singletons' : 'synth. 60%\nsingleton',
           'misassign-0.10-reassign' : 'synth. 10%\nreassign',
           'misassign-distance-0.03' : 'synth.\nneighbor 0.03',
           'mixcr' : 'MiXCR',
           'adj_mi' : 'adj MI',
           'ccf_under' : 'precision',
           'ccf_over' : 'sensitivity',
           'ccf_product' : 'F1 score'
           }

colors = {'true' : '#006600',
          'partition' : '#cc0000',  # 8c001a',
          'vsearch-partition' : '#990012',  #c04000',
          'naive-hamming-partition' : '#990012',
          'seed-partition' : '#990012',
          'seed-naive-hamming-partition' : '#990012',
          'vollmers-0.5' : '#3333ff',
          'vollmers-0.9' : '#3399ff',
          'changeo' :  '#2b65ec',
          'mixcr' : '#2b65ec',
          'misassign-0.60-singletons' : '#808080',
          'misassign-0.10-reassign' : '#808080',
          'misassign-distance-0.03' : '#808080'
}

linewidths = {'true' : 15,
              'vsearch-partition' : 3,
              'naive-hamming-partition' : 3,
              'seed-partition' : 2,
              'seed-naive-hamming-partition' : 2,
              'partition' : 6,
              'vollmers-0.5' : 4,
              'vollmers-0.9' : 6,
              'changeo' : 3,
              'mixcr' : 6,
              'misassign-0.60-singletons' : 4,
              'misassign-0.10-reassign' : 3,
              'misassign-distance-0.03' : 2
}

linestyles = {'naive-hamming-partition' : 'dashed',
              'vsearch-partition' : 'dotted',
              'changeo' : 'dashed',
              'mixcr' : 'dotted',
              'misassign-distance-0.03' : 'dashed'
}

alphas = {'true' : 0.6,
          'vollmers-0.9' : 0.6,
          'misassign-0.60-singletons' : 0.5,
          'misassign-distance-0.03' : 0.8
}

def label_bullshit_transform(label):
    return '-'.join([hex(int(l)) for l in label.split('-')]).replace('0x', '')

# linewidths['v-true'] = 10
# linewidths['cdr3-true'] = 10
# colors['v-true'] = '#006600'
# colors['cdr3-true'] = '#006600'
# colors['v-indels'] = '#cc0000'
# colors['cdr3-indels'] = '#cc0000'

# ----------------------------------------------------------------------------------------
def plot_cluster_size_hists(outfname, hists, title, xmax=None, log='x', normalize=False):
    if 'seaborn' not in sys.modules:
        import seaborn  # really #$*$$*!ing slow to import, but only importing part of it doesn't seem to help
    sys.modules['seaborn'].set_style('ticks')

    fsize = 20
    mpl.rcParams.update({
        # 'font.size': fsize,
        'legend.fontsize': fsize,
        'axes.titlesize': fsize,
        # 'axes.labelsize': fsize,
        'xtick.labelsize': fsize,
        'ytick.labelsize': fsize,
        'axes.labelsize': fsize
    })

    # base_xvals = hists['true'].get_bin_centers()
    # data = {}
    # for name, hist in hists.items():
    #     hist.normalize()

    #     contents = hist.bin_contents
    #     centers = hist.get_bin_centers()
    #     if len(centers) > len(base_xvals):
    #         print centers, base_xvals
    #         assert False
    #     for ic in range(len(base_xvals)):
    #         if ic < len(centers):
    #             if centers[ic] != base_xvals[ic]:
    #                 print centers
    #                 print base_xvals
    #                 assert False
    #         else:
    #             contents.append(0)

    #     data[name] = contents
        
    fig, ax = plt.subplots()
    fig.tight_layout()
    plt.gcf().subplots_adjust(bottom=0.16, left=0.2, right=0.78, top=0.95)
    # dark red '#A52A2A',
    plots = {}
    scplots = {}
    # tmpmax, n_queries = None, None
    for name, hist in hists.items():
        if 'misassign' in name:
            continue
        if 'vollmers' in name:
            if '0.7' in name or '0.8' in name or '0.95' in name or '0.5' in name:
                continue

        # other (old) possibility:
        # ax.bar and ax.scatter also suck
        # plots[name] = ax.plot(base_xvals, data[name], linewidth=linewidth, label=name, color=colors.get(name, 'grey'), linestyle=linestyle, alpha=alpha)
        # scplots[name] = ax.scatter(hists[name].get_bin_centers(), hists[name].bin_contents, linewidth=linewidths.get(name, 4), label=legends.get(name, name), color=colors.get(name, 'grey'), linestyle=linestyle, alpha=alpha)

        kwargs = {'linewidth' : linewidths.get(name, 4),
                  'label' : legends.get(name, name),
                  'color' : colors.get(name, 'grey'),
                  'linestyle' : linestyles.get(name, 'solid'),
                  'alpha' : alphas.get(name, 1.)}

        # was using this:
        if normalize:
            hist.normalize()
        plots[name] = ax.errorbar(hist.get_bin_centers(), hist.bin_contents_no_zeros(1e-8), yerr=hist.errors, **kwargs)
        # hist.mpl_plot(ax, remove_empty_bins=True, **kwargs)  # could maybe eventually switch to this, but probably better to just rewrite this whole fcn if I need to do anything

    legend = ax.legend()
    sys.modules['seaborn'].despine()  #trim=True, bottom=True)

    # xmax = tmpmax
    if xmax is None:
        xmax = plt.gca().get_xlim()[1]
    else:
        ax.set_xlim(0.9, xmax)

    if normalize:
        if 'vollmers' in title:
            ymin = 5e-4
        else:
            ymin = 5e-5
        plt.ylim(ymin, 1)
    plt.title(title)
    plt.xlabel('cluster size')
    plt.ylabel('fraction of clusters' if normalize else 'number of clusters')
    plt.subplots_adjust(bottom=0.14, left=0.2)
    if 'x' in log:
        ax.set_xscale('log')
    if 'y' in log:
        ax.set_yscale('log')
        # if n_queries is not None:
        #     plt.ylim(1./n_queries, 1)
    potential_xticks = [1, 2, 3, 9, 30, 75, 200, 500]
    xticks = [xt for xt in potential_xticks if xt < xmax]
    plt.xticks(xticks, [str(xt) for xt in xticks])
    plotdir = os.path.dirname(outfname)
    if not os.path.exists(plotdir):
        os.makedirs(plotdir)
    plt.savefig(outfname)
    plt.close()
    # subprocess.check_call(['chmod', '664', outfname])

# ----------------------------------------------------------------------------------------
def plot_metrics_vs_thresholds(meth, thresholds, info, plotdir, plotfname, title):
    fig, ax = mpl_init()
    if 'adj_mi' in info and meth in info['adj_mi']:
        ax.plot(thresholds, info['adj_mi'][meth], label='adj mi', linewidth=4)
    ax.plot(thresholds, info['ccf_under'][meth], label='clonal fraction', color='#cc0000', linewidth=4)
    ax.plot(thresholds, info['ccf_over'][meth], label='fraction present', color='#cc0000', linestyle='--', linewidth=4)
    ccf_products = [info['ccf_under'][meth][iv] * info['ccf_over'][meth][iv] for iv in range(len(thresholds))]
    ax.plot(thresholds, ccf_products, label='product of fractions', color='#006600', linewidth=4)
    log, xlabel = '', ''
    if meth == 'partition':
        xlabel = 'log prob ratio'
        ymin = 0.3  #0.69
        xticks = [b for b in range(int(thresholds[0]), int(thresholds[-1]), 5)]
        if int(thresholds[-1]) not in xticks:
            xticks.append(int(thresholds[-1]))
    elif meth == 'naive-hamming-partition' or meth == 'vsearch-partition':
        xlabel = 'naive hamming fraction'
        ymin = 0.3
        xticks = [th for th in thresholds if th < 0.12 and th != 0.025]
        log = 'x'
    mpl_finish(ax, plotdir, plotfname, log=log, xticks=xticks, xticklabels=xticks, leg_loc=(0.1, 0.2), xbounds=(xticks[0], xticks[-1]), ybounds=(ymin, 1.01), title=title, xlabel=xlabel, ylabel='metric value')

# ----------------------------------------------------------------------------------------
def plot_adj_mi_and_co(plotname, plotvals, mut_mult, plotdir, valname, xvar, title=''):
    if 'seaborn' not in sys.modules:
        import seaborn  # really #$*$$*!ing slow to import, but only importing part of it doesn't seem to help
    sys.modules['seaborn'].set_style('ticks')

    # ----------------------------------------------------------------------------------------
    def remove_some_duplicates(xyvals):
        hmap = {}
        newvals = []
        for x, y in xyvals:
            if x in hmap and x != 100000 and x != 500000 and x != 1000000:
                continue
            newvals.append((x, y))
            hmap.add(x)
        return newvals

    fig, ax = mpl_init()
    mpl.rcParams.update({
        'legend.fontsize': 15,})
    plots = {}
    for meth, xyvals in plotvals.items():

        # print sorted([xy[0] for xy in xyvals])
        # xyvals = remove_some_duplicates(xyvals)

        xyvals = sorted(xyvals, key=operator.itemgetter(0))
        xvals = [xy[0] for xy in xyvals]  # xyvals.keys()
        yvals = [ve[1][0] for ve in xyvals]
        yerrs = [ve[1][1] for ve in xyvals]
        kwargs = {'linewidth' : linewidths.get(meth, 4),
                  'label' : legends.get(meth, meth),
                  'color' : colors.get(meth, 'grey'),
                  'linestyle' : linestyles.get(meth, 'solid'),
                  'alpha' : alphas.get(meth, 1.),
                  }

        if meth == 'seed-partition':
            kwargs['linewidth'] = 0
            kwargs['alpha'] = 0.5

        if xvar == 'n_leaves':
            kwargs['fmt'] = '-o'
            plots[meth] = ax.errorbar(xvals, yvals, yerr=yerrs, **kwargs)
        else:  # darn it, the order in the legend gets messed up if I do some as .plot and some as .errorbar
            kwargs['marker'] = '.'
            kwargs['markersize'] = 20
            plots[meth] = ax.plot(xvals, yvals, **kwargs)
    
    lx, ly = 1.6, 0.7
    if len(plotvals) != 1:
        legend = ax.legend(bbox_to_anchor=(lx, ly))
    # legend.get_frame().set_facecolor('white')
    ymin = -0.01
    ax.set_ylim(ymin, 1.03)
    sys.modules['seaborn'].despine()  #trim=True, bottom=True)
    plt.title(title)
    xtitle = 'mean N leaves' if xvar == 'n_leaves' else 'sample size'
    plt.xlabel(xtitle)
    plt.ylabel(legends[valname])
    plt.gcf().subplots_adjust(bottom=0.14, left=0.12, right=0.67, top=0.95)

    xticks = xvals

    # put an 'n/a' in the n_leaves=1 column for adj_mi
    # if 1. not in xticks:
    #     xticks = [1, ] + xticks
    #     x1 = 1.
    #     ax.text(x1 - 0.25, 0.5, 'n/a', color='green', fontsize=25)
    #     ax.plot([x1, x1], [0.05, 0.4], color='green', linewidth=3)
    #     ax.plot([x1, x1], [0.6, 0.97], color='green', linewidth=3)
    # ax.set_xlim(xticks[0] - 0.4, xticks[-1])

    xticks = list(xvals)

    if xvar == 'n_leaves':
        ax.set_xscale('log')
        if 100 in xticks and 200 in xticks:
            xticks.remove(100)
        ax.set_xlim(0.95 * xvals[0], 1.05 * xvals[-1])
    elif xvar == 'nseqs':
        # xticks = [xticks[i] for i in range(0, len(xticks), 2)]
        # if 750 in xticks:
        #     xticks.remove(750)
        # xticks += xvals[-1:]
        # xticks = [100, 5000, 10000, 15000]
        xticks = [1000, 10000, 100000, 1000000]
        ax.set_xscale('log')
        ax.set_xlim(0.9 * xvals[0], 1.15 * xvals[-1])

    xticklabels = xticks if xvar == 'n_leaves' else ['%.0e' % xt for xt in xticks]
    plt.xticks(xticks, xticklabels)
    # ax.plot([xticks[0], xticks[-1]], [1., 1.], linewidth=1, color='grey')
    ax.grid(True)

    yticks = [yt for yt in [0., .2, .4, .6, .8, 1.] if yt >= ymin]
    yticklabels = [str(yt) for yt in yticks]
    plt.yticks(yticks, yticklabels)
    if not os.path.exists(plotdir):
        os.makedirs(plotdir)
    plt.savefig(plotdir + '/' + plotname)
    plt.close()

# ----------------------------------------------------------------------------------------
def mpl_init(figsize=None, fontsize=20):
    if 'seaborn' not in sys.modules:
        import seaborn  # really #$*$$*!ing slow to import, but only importing part of it doesn't seem to help
    sys.modules['seaborn'].set_style('ticks')
    fsize = fontsize
    mpl.rcParams.update({
        # 'legend.fontweight': 900,
        'legend.fontsize': fsize,
        'axes.titlesize': fsize,
        'xtick.labelsize': fsize,
        'ytick.labelsize': fsize,
        'axes.labelsize': fsize
    })
    fig, ax = plt.subplots(figsize=figsize)
    fig.tight_layout()
    plt.gcf().subplots_adjust(bottom=0.16, left=0.2, right=0.78, top=0.92)

    return fig, ax

# ----------------------------------------------------------------------------------------
def mpl_finish(ax, plotdir, plotname, title='', xlabel='', ylabel='', xbounds=None, ybounds=None, leg_loc=(0.04, 0.6), leg_prop=None, log='',
               xticks=None, xticklabels=None, xticklabelsize=None, yticklabelsize=None, yticks=None, yticklabels=None, no_legend=False, adjust=None, suffix='svg', leg_title=None, legend_fontsize=None):
    if 'seaborn' not in sys.modules:
        import seaborn  # really #$*$$*!ing slow to import, but only importing part of it doesn't seem to help
    if not no_legend:
        handles, labels = ax.get_legend_handles_labels()
        if len(handles) > 0:
            if len(handles) > 5:
                leg_loc = leg_loc[0], leg_loc[1] - 0.15
            legend = ax.legend(handles, labels, loc=leg_loc, prop=leg_prop, title=leg_title, fontsize=legend_fontsize)
    default_adjust = {'bottom' : 0.20, 'left' : 0.18, 'right' : 0.95, 'top' : 0.92}
    if adjust is not None:
        default_adjust.update(adjust)  # this makes things still work if the calling fcn has {} as the default rather than None
    plt.gcf().subplots_adjust(**default_adjust)  # ok, it's not default any more, but I don't want to change the name
    sys.modules['seaborn'].despine()  #trim=True, bottom=True)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    if 'x' in log:
        ax.set_xscale('symlog')  # 'log' used to work, but now it screws up the x axis labels
    if 'y' in log:
        ax.set_yscale('log')
    if xbounds is not None and xbounds[0] != xbounds[1]:
        plt.xlim(xbounds[0], xbounds[1])
    if ybounds is not None and ybounds[0] != ybounds[1]:
        plt.ylim(ybounds[0], ybounds[1])
    if xticks is not None:
        plt.xticks(xticks)
    if yticks is not None:
        plt.yticks(yticks)
    if xticklabels is not None:
        # mean_length = float(sum([len(xl) for xl in xticklabels])) / len(xticklabels)
        median_length = numpy.median([len(xl) for xl in xticklabels])
        if median_length > 4:
            ax.set_xticklabels(xticklabels, rotation='vertical', size=8 if xticklabelsize is None else xticklabelsize)
        else:
            ax.set_xticklabels(xticklabels, size=xticklabelsize)
    if yticklabels is not None:
        ax.set_yticklabels(yticklabels, size=yticklabelsize)
    plt.title(title, fontweight='bold', fontsize=20 if len(title) < 25 else 15)
    if not os.path.exists(plotdir):
        os.makedirs(plotdir)

    fullname = plotdir + '/' + plotname + '.' + suffix
    plt.savefig(fullname)
    plt.close()
    # subprocess.check_call(['chmod', '664', fullname])
    return fullname  # this return is being added long after this fcn was written, so it'd be nice to go through all the places where it's called and take advantage of the return value

# ----------------------------------------------------------------------------------------
def plot_cluster_similarity_matrix(plotdir, plotname, meth1, partition1, meth2, partition2, n_biggest_clusters, title='', debug=False):
    if debug:
        print ''
        print '%s    %s' % (meth1, meth2)
    # partition1 = [['4'], ['7', '8'], ['6', '5'], ['99', '3', '1']]
    # # partition2 = [['1', '2', '3'], ['4'], ['5', '6'], ['7', '8']]
    # partition2 = [['3'], ['5'], ['6'], ['7'], ['8'], ['99', '3', '4']]
    a_cluster_lengths, b_cluster_lengths, smatrix = utils.partition_similarity_matrix(meth1, meth2, partition1, partition2, n_biggest_clusters=n_biggest_clusters, debug=debug)
    if debug:
        print 'a_clusters: ', ' '.join([str(l) for l in a_cluster_lengths])
        print 'b_clusters: ', ' '.join([str(l) for l in b_cluster_lengths])

    fig, ax = plt.subplots()
    plt.gcf().subplots_adjust(bottom=0.14, left=0.18, right=0.95, top=0.92)
    ax.xaxis.set_ticks_position('bottom')
    ax.yaxis.set_ticks_position('left')
    data = numpy.array(smatrix)
    cmap = plt.cm.Blues  #cm.get_cmap('jet')
    cmap.set_under('w')
    heatmap = ax.pcolor(data, cmap=cmap, vmin=0., vmax=1.)
    cbar = plt.colorbar(heatmap)
    
    modulo = 2
    if n_biggest_clusters > 20:
        modulo = 3
    ticks = [n - 0.5 for n in range(1, n_biggest_clusters + 1, modulo)]
    xticklabels = [b_cluster_lengths[it] for it in range(0, len(b_cluster_lengths), modulo)]
    yticklabels = [a_cluster_lengths[it] for it in range(0, len(a_cluster_lengths), modulo)]
    plt.xticks(ticks, xticklabels)
    plt.yticks(ticks, yticklabels)

    mpl.rcParams['text.usetex'] = True
    mpl.rcParams['text.latex.unicode'] = True

    def boldify(textstr):
        textstr = textstr.replace('%', '\%')
        textstr = textstr.replace('\n', '')
        return r'\textbf{' + textstr + '}'

    plt.xlabel(boldify(legends.get(meth2, meth2)) + ' cluster size')  # I don't know why it's reversed, it just is
    plt.ylabel(boldify(legends.get(meth1, meth1)) + ' cluster size')
    ax.set_xlim(0, n_biggest_clusters)
    ax.set_ylim(0, n_biggest_clusters)

    plt.title(title)
    
    if not os.path.exists(plotdir):
        os.makedirs(plotdir)
    plt.savefig(plotdir + '/' + plotname + '.svg')
    plt.close()

# ----------------------------------------------------------------------------------------
def make_html(plotdir, n_columns=3, extension='svg', fnames=None, title='foop', new_table_each_row=False, htmlfname=None, extra_links=None):
    if fnames is not None:  # make sure it's formatted properly
        for rowfnames in fnames:
            if not isinstance(rowfnames, list):
                raise Exception('each entry in fnames should be a list of strings, but got a %s: %s' % (type(rowfnames), rowfnames))
            for fn in rowfnames:
                if not isinstance(fn, (str, unicode)):
                    raise Exception('each entry in each row should be a string (file name), but got a %s: %s' % (type(fn), fn))
    if plotdir[-1] == '/':  # remove trailings slash, if present
        plotdir = plotdir[:-1]
    if not os.path.exists(plotdir):
        raise Exception('plotdir %s d.n.e.' % plotdir)
    dirname = os.path.basename(plotdir)
    extra_link_str = ''
    if extra_links is not None:
        extra_link_str = ' '.join(['<a href=%s>%s</a>' % (url, name) for name, url in extra_links])
    lines = ['<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 3.2//EN>',
             '<html>',
             '<head><title>' + title + '</title></head>',
             '<body bgcolor="000000">', 
             '<h3 style="text-align:left; color:DD6600;">' + title + '</h3>',
             extra_link_str,
             '<table>',
             '<tr>']

    def add_newline(lines):
        if new_table_each_row:
            newlines = ['</tr>', '</table>', '<table>', '<tr>']
        else:
            newlines = ['</tr>', '<tr>']
        lines += newlines
    def add_fname(lines, fullfname):  # NOTE <fullname> may, or may not, be a base name (i.e. it might have a subdir tacked on the left side)
        fname = fullfname.replace(plotdir, '').lstrip('/')
        if htmlfname is None:  # dirname screws it up if we're specifying htmlfname explicitly, since then the files are in a variety of different subdirs
            fname = dirname + '/' + fname
        line = '<td><a target="_blank" href="' + fname + '"><img src="' + fname + '" alt="' + fname + '" width="100%"></a></td>'
        lines.append(line)

    # if <fnames> wasn't used to tell us how to group them into rows, try to guess based on the file base names
    if fnames is None:
        fnamelist = [os.path.basename(fn) for fn in sorted(glob.glob(plotdir + '/*.' + extension))]
        fnames = []

        # arrange the ones that have '[vdj]_' into group of three
        for v_fn in [fn for fn in fnamelist if os.path.basename(fn).find('v_') == 0]:  # get the ones that start with 'v_', so we can use them as templates for the others
            fstem = v_fn.replace('v_', '')
            fnames.append([rstr + fstem for rstr in plotconfig.rstrings if rstr + fstem in fnamelist])
            for fn in fnames[-1]:
                fnamelist.remove(fn)

        # and group insertion lengths and contents together
        found_bound_fnames = [fn for fn in fnamelist if any(b + '_insertion' == utils.getprefix(os.path.basename(fn)) for b in utils.all_boundaries)]
        if len(found_bound_fnames) == len(utils.all_boundaries):  # if we don't have all of them, we can't make a complete row, so just let them get grouped below
            fnames.append(found_bound_fnames)
            for fn in found_bound_fnames:
                fnamelist.remove(fn)
        found_content_fnames = [fn for fn in fnamelist if '_content' in fn]
        if len(found_content_fnames) > 0:
            fnames.append(found_content_fnames)
            for fn in found_content_fnames:
                fnamelist.remove(fn)

        # then do the rest in groups of <n_columns>
        while len(fnamelist) > 0:
            fnames.append(fnamelist[:n_columns])
            fnamelist = fnamelist[n_columns:]

    # write the meat of the html
    for rowlist in fnames:
        for fn in rowlist:
            add_fname(lines, fn)
        add_newline(lines)

    lines += ['</tr>',
              '</table>',
              '</body>',
              '</html>']

    if htmlfname is None:
        htmlfname = os.path.dirname(plotdir) + '/' + dirname + '.html'  # more verbose than necessary
    with open(htmlfname, 'w') as htmlfile:
        htmlfile.write('\n'.join(lines))
    # subprocess.check_call(['chmod', '664', htmlfname])

# ----------------------------------------------------------------------------------------
def make_allele_finding_plot(plotdir, gene, position, values, xmax, fitfos=None, new_gene=None):
    xmin, xmax = -0.3, xmax
    fig, ax = mpl_init()

    ax.errorbar(values['n_mutelist'], values['freqs'], yerr=values['errs'], markersize=15, linewidth=2, marker='.')  #, title='position ' + str(position))

    if fitfos is not None:  # fitted lines
        colors = {'prefo' : 'red', 'postfo' : 'red', 'onefo' : 'green'}
        for ftype in colors:
            if fitfos[ftype]['xvals'] is None:  # not really sure why this happens... probably zero-point fits?
                continue
            linevals = [fitfos[ftype]['slope']*x + fitfos[ftype]['y_icpt'] for x in fitfos[ftype]['xvals']]
            ax.plot(fitfos[ftype]['xvals'], linevals, color=colors[ftype])

    ax.plot([xmin, xmax], [0, 0], linestyle='dashed', alpha=0.5, color='black')
    ymax = max(values['freqs']) + max(values['errs'])
    title = 'position %d in %s' % (position, gene)
    if new_gene is not None:
        ax.text(0.3 * (xmax - xmin), 0.95 * (ymax - 0), 'inferred: %s' % new_gene, color='red', fontsize=15)
    mpl_finish(ax, plotdir, str(position), xlabel='mutations in %s segment' % utils.get_region(gene), ylabel='position\'s mut freq', xbounds=(xmin, xmax), ybounds=(-0.01, ymax), leg_loc=(0.95, 0.1), adjust={'right' : 0.85}, title=title)

# ----------------------------------------------------------------------------------------
def make_fraction_plot(hright, hwrong, plotdir, plotname, xlabel, ylabel, xbounds, only_csv=False, write_csv=False):
    if 'fraction_uncertainty' not in sys.modules:
        import fraction_uncertainty

    # NOTE should really merge this with draw_no_root()
    xvals = hright.get_bin_centers() #ignore_overflows=True)
    right = hright.bin_contents
    wrong = hwrong.bin_contents
    yvals = [float(r) / (r + w) if r + w > 0. else 0. for r, w in zip(right, wrong)]

    # remove values corresponding to bins with no entries
    while yvals.count(0.) > 0:
        iv = yvals.index(0.)
        xvals.pop(iv)
        right.pop(iv)
        wrong.pop(iv)
        yvals.pop(iv)

    tmphilos = [sys.modules['fraction_uncertainty'].err(r, r + w) for r, w in zip(right, wrong)]
    yerrs = [err[1] - err[0] for err in tmphilos]
    # print '%s' % region
    # for iv in range(len(xvals)):
    #     print '   %5.2f     %5.0f / %5.0f  =  %5.2f   +/-  %.3f' % (xvals[iv], right[iv], right[iv] + wrong[iv], yvals[iv], yerrs[iv])

    if write_csv:
        hist_for_csv = Hist(hright.n_bins, hright.xmin, hright.xmax)
        bincenters = hright.get_bin_centers()
        for ibin in range(hright.n_bins):
            bcenter = bincenters[ibin]
            if bcenter in xvals:  # if we didn't remove it
                iy = xvals.index(bcenter)
                hist_for_csv.set_ibin(ibin, yvals[iy], error=yerrs[iy])

        hist_for_csv.write(plotdir + '/' + plotname + '.csv')

    if not only_csv:
        fig, ax = mpl_init()
        ax.errorbar(xvals, yvals, yerr=yerrs, markersize=10, linewidth=1, marker='.')
        if xlabel == 'support':
            ax.plot((0, 1), (0, 1), color='black', linestyle='--', linewidth=3)  # line with slope 1 and intercept 0
        mpl_finish(ax, plotdir, plotname, xlabel=xlabel, ylabel=ylabel, title=plotconfig.plot_titles.get(plotname, plotname), xbounds=xbounds, ybounds=(-0.1, 1.1))

    plt.close()

# ----------------------------------------------------------------------------------------
def plot_gl_inference_fractions(plotdir, plotname, plotvals, labels, xlabel='', ylabel='', leg_title=None, title=None):
    if 'fraction_uncertainty' not in sys.modules:
        import fraction_uncertainty
    fraction_uncertainty = sys.modules['fraction_uncertainty']

    def get_single_vals(pv):
        yvals = [float(c) / t for c, t in zip(pv['ycounts'], pv['ytotals'])]  # total shouldn't be able to be zero
        tmphilos = [fraction_uncertainty.err(c, t) for c, t in zip(pv['ycounts'], pv['ytotals'])]
        yerrs = [err[1] - err[0] for err in tmphilos]
        print '  %s                    %s' % (xlabel, ylabel)
        for iv in range(len(pv['xvals'])):
            print '   %8.0f     %5.0f / %-5.0f  =  %5.2f   +/-  %.3f' % (pv['xvals'][iv], pv['ycounts'][iv], pv['ytotals'][iv], yvals[iv], yerrs[iv])
        return pv['xvals'], yvals, yerrs

    fig, ax = mpl_init()
    mpl.rcParams.update({'legend.fontsize' : 15})

    xmin, xmax, xticks = None, None, None
    for ii in range(len(labels)):
        print labels[ii]
        xvals, yvals, yerrs = get_single_vals(plotvals[ii])
        if xmin is None:
            xmin = xvals[0]
            xmax = xvals[-1]
            xticks = xvals
        kwargs = {
            'markersize' : 13,
            'linewidth' : default_linewidths[min(ii, len(default_linewidths) - 1)],
            'color' : default_colors[min(ii, len(default_colors) - 1)],
            'alpha' : 0.6,
        }
        ax.errorbar(xvals, yvals, yerr=yerrs, label=labels[ii], **kwargs)

    minfrac, maxfrac = 0.95, 1.05
    ax.plot((minfrac * xmin, maxfrac * xmax), (0, 0), color='black', linestyle='--', linewidth=3)  # line at y=0
    ax.plot((minfrac * xmin, maxfrac * xmax), (1, 1), color='black', linestyle='--', linewidth=3)  # line at y=1
    mpl_finish(ax, plotdir, plotname, xlabel=xlabel, ylabel=ylabel, xbounds=(minfrac*xmin, maxfrac*xmax), ybounds=(-0.05, 1.05), log='x', xticks=xticks, xticklabels=[('%d' % x) for x in xticks], leg_loc=(0.8, 0.55 + 0.05*(4 - len(plotvals))), leg_title=leg_title, title=title)
    plt.close()

# ----------------------------------------------------------------------------------------
def plot_laplacian_spectra(plotdir, plotname, eigenvalues, title):
    hist = Hist(30, min(eigenvalues), max(eigenvalues), value_list=eigenvalues)
    fig, ax = mpl_init()
    hist.mpl_plot(ax)
    mpl_finish
    mpl_finish(ax, plotdir, plotname, xlabel='eigenvalues', ylabel='count', title=title)

# ----------------------------------------------------------------------------------------
# if <high_x_val> is set, clusters with median x above <high_x_val> get skipped by default and returned, the idea being that you call this fcn again at the end with <plot_high_x> set just on the thereby-returned high-x clusters
def make_single_joyplot(sorted_clusters, annotations, repertoire_size, plotdir, plotname, x1key='n_mutations', x1label='N mutations', x2key=None, x2label=None, high_x_val=None, plot_high_x=False,
                        cluster_indices=None, title=None, queries_to_include=None, global_max_vals=None, debug=False):
    import lbplotting
    all_metrics = treeutils.lb_metrics.keys() + treeutils.dtr_metrics
    # NOTE <xvals> must be sorted
    # ----------------------------------------------------------------------------------------
    def offcolor(offset):
        offcolors = {'up' : '#386cc2', 'down' : '#bf1328'}  # greyish blue, mild red
        return offcolors[offset]
    # ----------------------------------------------------------------------------------------
    def bexpand(bpair, fuzz=0.02):
        diff = bpair[-1] - bpair[0]
        return [bpair[0] - fuzz * diff, bpair[1] + fuzz * diff]
    # ----------------------------------------------------------------------------------------
    def get_xval_list(cluster, xkey):
        line = annotations[':'.join(cluster)]
        if xkey in all_metrics:
            return [line['tree-info']['lb'][xkey][u] for u in line['unique_ids']]  # we can't use .values() because there's lb values in the dict in 'tree-info' that don't correspond to uids in 'unique_ids' (and we don't want to include those values)
        else:
            return line[xkey]
    # ----------------------------------------------------------------------------------------
    def get_xval_dict(uids, xkey):
        line = annotations[':'.join(cluster)]
        if xkey in all_metrics:
            return {u : line['tree-info']['lb'][xkey][u] for u in uids}
        else:
            return {u : utils.per_seq_val(line, xkey, u) for u in uids}
    # ----------------------------------------------------------------------------------------
    def getbounds(xkey):
        all_xvals = [x for c in sorted_clusters for x in get_xval_list(c, xkey)]
        if len(all_xvals) == 0:
            return None
        bounds = [f(all_xvals) for f in [min, max]]
        if global_max_vals is not None and xkey in global_max_vals:
            bounds[1] = global_max_vals[xkey]
        return bounds
    # ----------------------------------------------------------------------------------------
    def uselog(xkey):  # the low end (zero bin) of these distributions always dominates, but we're actually interested in the upper tail, so logify it
        return xkey in all_metrics or xkey == 'affinities'
    # ----------------------------------------------------------------------------------------
    def add_hist(xkey, xvals, yval, iclust, cluster, median_x1, fixed_x1max, base_alpha, offset=None):
        qti_x_vals = {}
        if queries_to_include is not None:
            queries_to_include_in_this_cluster = set(cluster) & set(queries_to_include)
            if len(queries_to_include_in_this_cluster) > 0:
                qti_x_vals = get_xval_dict(queries_to_include_in_this_cluster, xkey)  # add a red line for each of 'em (i.e. color that hist bin red)
                if plot_high_x:
                    xfac = 1.1
                elif float(median_x1) / fixed_x1max < 0.5:
                    xfac = 0.75
                else:
                    xfac = 0.1
                ax.text(xfac * fixed_x1max, yval, ' '.join(sorted(queries_to_include_in_this_cluster, key=lambda q: qti_x_vals[q])), color='red', fontsize=8)

        if debug:
            fstr = '6.1f' if xkey == 'n_mutations' else '6.4f'
            print ('     %5s  %-10s  %4.1f  %'+fstr+'  %'+fstr) % ('%d' % csize if iclust == 0 else '', repfracstr if iclust == 0 else '', yval, numpy.median(xvals), numpy.mean(xvals))

        if xkey == 'n_mutations':
            nbins = xvals[-1] - xvals[0] + 1
            hist = Hist(nbins, xvals[0] - 0.5, xvals[-1] + 0.5)
        else:
            nbins = 30 if xkey in all_metrics else 15
            hist = Hist(nbins, *bexpand(xbounds[xkey], fuzz=0.01))
        hist.list_fill(xvals)
        if uselog(xkey):
            hist.logify(0.3)  # the factor is kind of arbitrary, but we need to set the scale for the smallest bin contents (in this case 1)
        assert hist.overflow_contents() == 0.  # includes underflows
        max_contents = max(hist.bin_contents)
        for ibin in range(1, hist.n_bins + 1):
            barheight = utils.intexterpolate(0., min_bar_height, max_contents, max_bar_height, hist.bin_contents[ibin])
            color = base_color
            if offset is None:
                y_lower, y_upper = yval - barheight/2, yval + barheight/2
            else:
                y_lower, y_upper = yval, yval
                color = offcolor(offset)
                if offset == 'up':
                    y_upper += barheight / 2
                elif offset == 'down':
                    y_lower -= barheight / 2
                else:
                    assert False
            alpha = base_alpha
            # alpha = utils.intexterpolate(0, min_alpha, max_contents, max_alpha, hist.bin_contents[ibin])
            for xtmp in qti_x_vals.values():
                if hist.find_bin(xtmp) == ibin:
                    color = 'red'
            if hist.bin_contents[ibin] == 0.:
                color = 'grey'
                alpha = 0.4
            xlo, xhi = hist.low_edges[ibin], hist.low_edges[ibin+1]
            if xkey == x2key:  # if it's the second one, we need to rescale the x vals to correspond to the existing x1key x axis
                xlo, xhi = [utils.intexterpolate(xbounds[x2key][0], xbounds[x1key][0], xbounds[x2key][1], xbounds[x1key][1], x) for x in [xlo, xhi]]
            ax.fill_between([xlo, xhi], [y_lower, y_lower], [y_upper, y_upper], color=color, alpha=alpha)

    # ----------------------------------------------------------------------------------------
    colors = ['#006600', '#3399ff', '#ffa500']
    # goldenrod '#daa520'
    # red '#cc0000',
    # dark red '#990012'
    # purple '#a821c7'
    # grey '#808080'

    dpi = 80
    xpixels = 450
    min_ypixels = 400
    total_delta_y = len(sorted_clusters)
    ypixels = max(min_ypixels, 10 * total_delta_y)
    fig, ax = mpl_init(figsize=(xpixels / dpi, ypixels / dpi))
    min_bar_height, max_bar_height = 0.3 / min_ypixels * total_delta_y, (12. if x2key is None else 25.) / min_ypixels * total_delta_y
    # min_alpha, max_alpha = 0.1, 1.
    base_alpha = 0.55

    ymin, ymax = 9999, 0
    iclust_global = 0  # index within this plot
    yticks, yticklabels = [], []

    high_x_clusters = []
    xbounds = {x1key : getbounds(x1key)}  # these are the smallest/largest x values in any of <sorted_clusters>, whereas <high_x_val> is a fixed calling-fcn-specified value that may be more or less (kind of wasteful to get all the x vals here and then also in the main loop)
    if x2key is not None:
        xbounds[x2key] = getbounds(x2key)
    if any(xbounds[xk] is None for xk in xbounds):
        return 'no values' if high_x_val is None else high_x_clusters  # 'no values' isn't really a file name, it just shows up as a dead link in the html
    fixed_xmax = high_x_val if high_x_val is not None else xbounds[x1key][1]  # xmax to use for the plotting (ok now there's three max x values, this is getting confusing)

    if debug:
        print '  %s   %d x %d   %s' % (plotname, xpixels, ypixels, utils.color('red', 'high %s'%x1key) if plot_high_x else '')
        print '      size   frac      yval    median   mean'

    if x2key is None:
        cgroup_iter = itertools.groupby(sorted_clusters, key=lambda c: len(c))  # this doesn't re-sort anything, it just creates groups by size (like |sort|uniq)
    else:
        cgroup_iter = [(len(c), [c]) for c in sorted_clusters]  # creates a structure similar to the previous clause, but with just trivial groups (one for each cluster), since in this case the clusters aren't sorted by size (and are instead sorted with continuous-valued variables) so we don't need/want the groupby stuff to a get decent y axis
    for csize, cluster_group in cgroup_iter:
        if x2key is None:
            cluster_group = sorted(list(cluster_group), key=lambda c: numpy.median(get_xval_list(c, x1key)))  # sort ties in the default sorting by median <x1key> (has no effect if x2key is set since the groups are always length 1)
        repfracstr = utils.get_repfracstr(csize, repertoire_size)
        for iclust, cluster in enumerate(cluster_group):
            x1vals = sorted(get_xval_list(cluster, x1key))
            median_x1 = numpy.median(x1vals)  # maybe should use mean instead of median?

            if high_x_val is not None and median_x1 > high_x_val and not plot_high_x:  # if <high_x_val> is not set, we don't skip any clusters
                high_x_clusters.append(cluster)
                continue

            yval = len(sorted_clusters) - iclust_global
            if yval < ymin:
                ymin = yval
            if yval > ymax:
                ymax = yval
            yticks.append(yval)
            yticklabels.append(repfracstr if x2key is None else '%d'%csize)

            base_color = colors[iclust_global % len(colors)]

            add_hist(x1key, x1vals, yval, iclust, cluster, median_x1, fixed_xmax, base_alpha, offset=None if x2key is None else 'up')
            if x2key is not None:
                tmpval = lbplotting.mean_of_top_quintile(x1vals)
                ax.plot([tmpval, tmpval], [yval, yval + 1./4], linewidth=2.5, alpha=0.55, color='green')
                x2vals = sorted(get_xval_list(cluster, x2key))
                add_hist(x2key, x2vals, yval, iclust, cluster, median_x1, fixed_xmax, base_alpha, offset='down')

            if cluster_indices is not None:  # add the (global) cluster index (i.e. 1 - rank) and cluster size as text on the right side of the plot
                xtext = x1vals[-1] if plot_high_x else fixed_xmax
                xwidth = ax.get_xlim()[1] - ax.get_xlim()[0] if plot_high_x else fixed_xmax
                if iclust_global == 0:
                    ax.text(0.05 * xwidth + xtext - 3, yval + 1, 'index', color=base_color, fontsize=6, alpha=base_alpha, fontdict={'weight' : 'bold'})
                    ax.text(0.12 * xwidth + xtext - 1, yval + 1, 'size', color=base_color, fontsize=6, alpha=base_alpha, fontdict={'weight' : 'bold'})
                ax.text(0.05 * xwidth + xtext, yval, str(cluster_indices[':'.join(cluster)]), color=base_color, fontsize=6, alpha=base_alpha, fontdict={'weight' : 'bold'})
                ax.text(0.12 * xwidth + xtext, yval, str(csize), color=base_color, fontsize=6, alpha=base_alpha, fontdict={'weight' : 'bold'})

            iclust_global += 1

    if x2key is not None:
        fig.text(0.8, 0.25, x1label if not uselog(x1key) else '%s (log)'%x1label, color=offcolor('up'), alpha=base_alpha, fontdict={'weight' : 'bold'})
        fig.text(0.85, 0.215, x2label if not uselog(x2key) else '%s (log)'%x2label, color=offcolor('down'), alpha=base_alpha, fontdict={'weight' : 'bold'})

    plot_x_bounds = [high_x_val, xbounds[x1key][1]] if plot_high_x else bexpand((xbounds[x1key][0], fixed_xmax))
    n_x_ticks, xlabel, xticks, xticklabels = 4, x1label, None, None
    if x2key is not None:
        xlabel = x2label
        xticks = [x for x in numpy.arange(xbounds[x1key][0], xbounds[x1key][1], (xbounds[x1key][1] - xbounds[x1key][0]) / (n_x_ticks-1))] + [xbounds[x1key][1]]
        xticklabels = ['%.1f' % utils.intexterpolate(xbounds[x1key][0], xbounds[x2key][0], xbounds[x1key][1], xbounds[x2key][1], x) for x in xticks]  # translate x1 tick positions to x2 tick labels
        fig.text(0.22, 0.1, '%.3f'%xbounds[x1key][0], color=offcolor('up'), alpha=base_alpha, fontdict={'weight' : 'bold'})
        fig.text(0.9, 0.1, '%.3f'%xbounds[x1key][1], color=offcolor('up'), alpha=base_alpha, fontdict={'weight' : 'bold'})
        fig.text(0.55, 0.05, x1label, color=offcolor('up'), alpha=base_alpha, fontdict={'weight' : 'bold'})
        fig.text(0.05, 0.9, 'sorted by\nmax %s'%x1label, color=offcolor('up'), alpha=base_alpha, fontdict={'weight' : 'bold'})
    n_y_ticks = 5
    if x2key is None and len(yticks) > n_y_ticks:
        yticks = [yticks[i] for i in range(0, len(yticks), int(len(yticks) / float(n_y_ticks - 1)))]
        yticklabels = [yticklabels[i] for i in range(0, len(yticklabels), int(len(yticklabels) / float(n_y_ticks - 1)))]
    fn = mpl_finish(ax, plotdir, plotname, xlabel=xlabel, ylabel=('family size (frac. of %d)' % repertoire_size) if x2key is None else 'clonal family size', title=title,
                    xbounds=plot_x_bounds, ybounds=bexpand((ymin, ymax), fuzz=0.03 if x2key is None else 0.07), xticks=xticks, xticklabels=xticklabels, yticks=yticks, yticklabels=yticklabels, yticklabelsize=11, adjust={'left' : 0.2, 'right' : 0.85})

    if high_x_val is None:
        return fn
    else:
        return high_x_clusters
