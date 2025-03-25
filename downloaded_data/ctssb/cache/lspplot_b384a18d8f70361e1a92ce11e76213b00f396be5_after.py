#!/usr/bin/env python2
'''
For plotting sclr/flds files.
'''
from docopt import docopt;
from lspreader import misc,read;
from lspreader import flds as fldsm;
from lspreader.lspreader import get_header;
import numpy as np;
import numpy.linalg as lin;
from pys import parse_ftuple,test,takef,mk_getkw;
from consts import *

pc_defaults = {
    'xlabel':'microns',
    'ylabel':'microns',
    'title':'',
};


def pc(q,p,**kw):
    def getkw(l):
        if test(kw,l):
            return kw[l];
        return pc_defaults[l];
    from matplotlib.colors import LogNorm;
    import matplotlib;
    if test(kw,"agg"):
        matplotlib.use("agg");
    import matplotlib.pyplot as plt;
    if not test(kw,"axes"):
        kw['axes'] = plt.axes();
    ret={};
    ax = ret['axes'] = kw['axes'];
    if test(kw,'log'):
        norm= LogNorm();
        q  += 1;
    else:
        norm= None;
    if test(kw, 'lims'):
        mn, mx = kw['lims'];
    else:
        mn, mx = 0, 1e2;  
    x,y=p;
    ret['q'] = q;
    ret['x'],ret['y'] = x,y;
    mypc = ret['pc'] =ax.pcolormesh(
        y,x,q,vmin=mn,vmax=mx,cmap='viridis',norm=norm);
    cbar = ret['cbar'] = plt.colorbar(mypc);
    if "clabel" in kw and kw["clabel"] is False:
        pass;
    else:
        cbar.set_label(getkw("clabel"));
    ax.set_xlabel(getkw("xlabel"));
    ax.set_ylabel(getkw("ylabel"));
    ax.set_title(getkw("title"));
    return ret;

def highlight(ret, val,
              q=None, color='white', alpha=0.15):
    ax = ret['axes'];
    if q is None:
        q = ret['q'];
    if not test(ret, 'cbar'):
        ret['cbar'] = plt.colorbar(ret['pc']);
    cbar = ret['cbar'];
    if not test(ret, 'cts'):
        ret['cts'] = [];
    ct = ax.contour(ret['y'],ret['x'], q, [val],
                    colors=[color], alpha = alpha);
    ret['cts'].append(ct);
    if q is ret['q']:
        cbar.add_lines(ct);
    return ret;

trajdefaults = dict(
    alpha = 0.15,
    coords= ['y','x'],
    color = 'black',
    no_resize=False,
    cmap='plasma',
    color_quantity=None,
    marker='o',
    size=1,
    lw=0,
);
    
def trajectories(ret,trajs,**kw):
    getkw=mk_getkw(kw, trajdefaults);
    x,y = getkw("coords");
    if not test(kw, "no_resize"):
        xlim, ylim = ret['axes'].get_xlim(), ret['axes'].get_ylim();
    if not test(kw,"color_quantity"):
        plotit = lambda itr: ret['axes'].plot(
            itr[x], itr[y],
            lw=0.1,
            c=getkw('color'),alpha=getkw('alpha'));
        pass;
    else:
        cf = getkw('color_quantity');
        if type(cf) == str:
            cf = lambda itr: itr[cf];
        plotit = lambda itr: ret['axes'].scatter(
            itr[x], itr[y],
            c=cf(itr),
            lw=getkw('lw'),
            s=getkw('size'),
            cmap=getkw('cmap'));
    for itr in np.rollaxis(trajs,1):
        plotit(itr);
    if not test(kw, "no_resize"):
        ret['axes'].set_xlim(xlim);
        ret['axes'].set_ylim(ylim);
