import getroot
import plotbase

import matplotlib
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import AxesGrid
import numpy as np 

plots = []

#plotting function for variations
def twoD_all(quantity, datamc, opt):
    for variation_quantity in ['npv', 'jet1eta','zpt']:
        for change in plotbase.getvariationlist(variation_quantity, opt):
            twoD(quantity, datamc, opt, changes=change, folder=variation_quantity)


# Main 2d Plotting module
def twoD(quantity, files, opt, fig_axes=(), changes=None, settings=None):

    # if no settings are given, create:
    settings = plotbase.getsettings(opt, changes, settings, quantity)   
    print "A %s plot is created with the following selection: %s" % (quantity, 
                                                          settings['selection'])

    settings['legloc'] = "None"

    datamc, rootobjects = [], []
    settings['events'] = []
    for f in files:
        rootobjects += [getroot.getobjectfromtree(quantity, f, settings, twoD=True)]
        rootobjects[-1].Sumw2()
        rootobjects[-1].Rebin2D(settings['rebin'], settings['rebin'])
        datamc += [getroot.root2histo(rootobjects[-1], f.GetName(), [1, 1])]
        settings['events'] += [datamc[-1].ysum()]

    if settings['ratio'] and len(datamc)==2:
        print "hallo"
        scaling_factor = datamc[0].binsum() / datamc[1].binsum()
        rootobjects[1].Scale(scaling_factor)
        rootobjects[0].Divide(rootobjects[1])
        rootobjects = [rootobjects[0]]       
        datamc = [getroot.root2histo(rootobjects[0], f.GetName(), [1, 1])]

    if len(quantity.split("_")) == 2:
        # normalize to the same number of events
        if len(datamc) > 1 and settings['normalize']:
            for d in datamc[1:]:
                if d.binsum() > 0.0 and datamc[0].binsum() > 0:
                    d.scale(datamc[0].binsum() / d.binsum() )
        z_name = 'Events'
        if settings['z'] is None:
            settings['z'] = [0, np.max(datamc[0].BinContents)]
    else:
        if settings['z'] is None:
            settings['z'] = plotbase.getaxislabels_list(quantity.split("_")[0])[:2]
        z_name = quantity.split("_")[0]
    
    # special dictionary for z-axis scaling (do we need this??)
    # 'quantity':[z_min(incut), z_max(incut), z_min(allevents), z_max(allevents)]
    z_dict = {
        'jet1pt':[0, 120, 0, 40],
        'jet2pt':[0, 40, 0, 40],
        'METpt':[15, 30, 15, 30],
        'ptbalance':[0.85, 1.1, 1, 4],
        'genzmass':[89, 93, 90.5, 92.5],
        'genzetarapidityratio':[1, 3, 0, 5]
    }

    #determine plot type: 2D Histogram or 2D Profile, and get the axis properties

    if settings['subplot']==True:
        fig = fig_axes[0]
        grid = [fig_axes[1]]
    else: 
        # create figure  + axes
        fig = plt.figure(figsize=(10.*len(datamc), 7.))
        grid = AxesGrid(fig, 111,
                        nrows_ncols = (1, len(datamc)),
                        axes_pad = 0.4,
                        share_all=True,
                        aspect=False,
                        label_mode = "L",
                        cbar_pad = 0.2,
                        cbar_location = "right",
                        cbar_mode='single',
                        )

       
    for plot, label, ax in zip(datamc, settings['labels'], grid):
        ax.set_title(label)

        cmap1 = matplotlib.cm.get_cmap('jet')
        image = ax.imshow(plot.BinContents,
            interpolation='nearest',
            cmap=cmap1,
            origin='lower',
            aspect = 'auto',
            extent = [plot.xborderlow, plot.xborderhigh, plot.yborderlow, plot.yborderhigh],
            vmin=settings['z'][0],
            vmax=settings['z'][1])

        # labels:
        """if 'data' not in label: mc = True
        else: mc = False
        if not subplot: plotbase.labels(ax, opt, legloc=False, frame=True, changes=change, jet=False,
                                        sub_plot=subplot, mc=mc, color='white', energy_label=(not subplot))
        """
 
        plotbase.axislabels(ax, settings['xynames'][0], settings['xynames'][1], 
                                                            settings=settings)
        plotbase.labels(ax, opt, settings, settings['subplot'])
        plotbase.setaxislimits(ax, settings)

    if settings['subplot']: return

    #add the colorbar
    cb = fig.colorbar(image, cax = grid.cbar_axes[0], ax=ax)
    cb.set_label(z_name)


    # create filename + folder
    settings['filename'] = plotbase.getdefaultfilename(quantity, opt, settings)

    plotbase.Save(fig, settings['filename'], opt)




def ThreeD(files, opt, changes={}, rebin=[2,2]):
    from mpl_toolkits.mplot3d import Axes3D
    from matplotlib import cm
    import numpy as np
    import random

    change= plotbase.getchanges(opt, changes)
    change['incut']='allevents'
    datamc = [getroot.getplotfromnick("2D_jet1eta_jet1phi", f,change, rebin) for f in files[1:]]

    # create supporting points
    x = np.linspace(-5,5,100/rebin[0])
    y = np.linspace(-3.2,3.2,100/rebin[1])
    X,Y = np.meshgrid(x,y)

    # create numpy array
    Z = np.array(datamc[0].BinContents)


    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    # 
    ax.plot_surface(X, Y, Z, rstride=1, cstride=1, cmap=cm.jet, linewidth=0)

    # set label + limits
    ax.set_zlim3d(0, datamc[0].maxBin())
    ax.set_xlabel(r'$\eta$')
    ax.set_ylabel(r'$\phi$')

    n = 360
    for i in range(n):

        # rotate viewing angle
        ax.view_init(20,-120+(360/n)*i)

        """if (i % 2 == 0):
            ax.text(0, 0, 11000, "WARNING!!!", va='top', ha='left', color='red', size='xx-large')
        ax.text(0, 0, 9800, "critical spike detected!", va='top', ha='left', color='black')
        ax.text(0, 0, 9100, str(random.random())+str(random.random())+str(random.random()), va='top', ha='center', color='black')"""

        # create filename + save
        plotbase.Save(fig, str(i).zfill(3), opt)

