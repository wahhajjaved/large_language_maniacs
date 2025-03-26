# -*- coding: utf-8 -*-
"""

Copyright (C) 2015 Stuart W.D Grieve 2015

Developer can be contacted by s.grieve _at_ ed.ac.uk

This program is free software;
you can redistribute it and/or modify it under the terms of the
GNU General Public License as published by the Free Software Foundation;
either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY;
without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the
GNU General Public License along with this program;
if not, write to:
Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor,
Boston, MA 02110-1301
USA

Collection of routines to generate a 4 panel study area figure with 
dimensions suitable for publication.

Creates an outline of a country, with internal adminsitrative boundaries with 
study area points marked and annotated from corresponding shapefiles.

Then loads 4 hillshade rasters in flt format and tiles them with correct UTM 
coordinates and labels them according to the labels in the countyr outline.

Finally, it combines these 2 images into a single plot which is publication ready.

Inputs: Shapefiles of country outline, state borders [if not needed load the outline twice],
        and a point shapefile of the study site locations
        
        4 hillshade files of the study areas in flt format
        
See the method Make_The_Figure() to understand how to supply these input files.

To Do:
    
    Get hillshade center dynamically to make code portable
    Cope with no state borders more gracefully
    Set up keyword args
    expose hillshdae size padding (currently 2000)
    expose image trim param
    remove needless rcparams
    figure out how to plot axis ticks with >4 locations
    modify code to cope with 1 -> 8 study areas [memory issues?]
    include code to have odd numbers of study sites
    

Created on Fri May 29 13:22:19 2015

@author: Stuart Grieve
"""


def mm_to_inch(mm):
    return mm*0.0393700787

def Draw_Outline(Country_Outline,State_Borders,Points):

    import matplotlib.pyplot as plt
    from matplotlib import rcParams
    import shapefile as shp
        
    # Set up fonts for plots
    rcParams['font.family'] = 'sans-serif'
    rcParams['font.sans-serif'] = ['arial']
    rcParams['font.size'] = 12
    rcParams['xtick.direction'] = 'out'
    rcParams['ytick.direction'] = 'out'
        
    fig = plt.figure()
    
    ax = plt.gca()
    
    #load shapefile here and add in the centre points of the DEMs as points on the shapefile
    #http://eric.clst.org/Stuff/USGeoJSON
    sf = shp.Reader(Country_Outline)
    
    for shape in sf.shapes():
        x=[]
        y=[]
        for point in shape.points:
            x.append(point[0])
            y.append(point[1])
        plt.plot(x,y,'k-',linewidth=0.5,alpha=0.25)
    
    sf = shp.Reader(State_Borders)#"polygon_project.shp"
    
    for shape in sf.shapes():
        x=[]
        y=[]
        for point in shape.points:
            x.append(point[0])
            y.append(point[1])
        plt.plot(x,y,'k-',linewidth=1)
    
    sf = shp.Reader(Points)
    
    px=[]
    py=[]
    for shape in sf.shapes():
        for point in shape.points:
            px.append(point[0])
            py.append(point[1])
        plt.plot(px,py,'r.')
    
    #suppress the ticks and labels
    ax.xaxis.set_visible(False)
    ax.yaxis.set_visible(False)
    ax.axis('off')
    ax.set_aspect('equal', adjustable='box')
    
    #label the points
    
    #NC
    ax.annotate('a', xy=(px[1]-450000,py[1]), xycoords='data', fontsize=14, horizontalalignment='left', verticalalignment='center')
    
    #OR
    ax.annotate('b', xy=(px[0]-450000,py[0]), xycoords='data', fontsize=14, horizontalalignment='left', verticalalignment='center')
    
    #GM
    ax.annotate('c', xy=(px[2]-450000,py[2]), xycoords='data', fontsize=14, horizontalalignment='left', verticalalignment='center')
    
    #CA
    ax.annotate('d', xy=(px[3]+300000,py[3]), xycoords='data', fontsize=14, horizontalalignment='left', verticalalignment='center')
    
    
    fig.set_size_inches(mm_to_inch(190), mm_to_inch(40))
        
    plt.savefig('Outline.png', dpi = 500)
    return 'Outline.png'

def Merge_Hillshades(files):
    
    import matplotlib.pyplot as plt
    import numpy as np
    import matplotlib.cm as cmx
    from matplotlib import rcParams
    import raster_plotter_simple as raster
            
    # Set up fonts for plots
    rcParams['font.family'] = 'sans-serif'
    rcParams['font.sans-serif'] = ['arial']
    rcParams['font.size'] = 12
    rcParams['xtick.direction'] = 'out'
    rcParams['ytick.direction'] = 'out'
        
    fig = plt.figure()
    
    labels = ['a','b','c','d']
    
    for i in range(1,5):
        
        ax = plt.subplot(2,2,i)
        
        #get data
        hillshade, hillshade_header = raster.read_flt(files[i-1])
       
        #ignore nodata values    
        hillshade = np.ma.masked_where(hillshade == -9999, hillshade)    
        
        x_max = hillshade_header[0]
        x_min = 0
        y_max = hillshade_header[1] 
        y_min = 0
        
        #plot the hillshade on the axes
        plt.imshow(hillshade, vmin=0, vmax=255, cmap=cmx.gray) 
    
        #place axis ticks around the outside of each plot
        if (i == 1): #top left  
            ax.xaxis.tick_top() 
            plt.tick_params(axis='x', which='both', bottom='off',length=2)
            plt.tick_params(axis='y', which='both', right='off',length=2)
        if (i == 2): #top right        
            ax.xaxis.tick_top()
            ax.yaxis.tick_right()
            plt.tick_params(axis='x', which='both', bottom='off',length=2)
            plt.tick_params(axis='y', which='both', left='off',length=2)
        if (i == 3): #bottom left        
            plt.tick_params(axis='x', which='both', top='off',length=2)
            plt.tick_params(axis='y', which='both', right='off',length=2) 
            plt.ylabel('Northing (m)', size=14,color='white') #create an invisible label here to create the padding for the real label later on
            ax.yaxis.labelpad = 10
        if (i == 4): #bottom right
            ax.yaxis.tick_right()        
            plt.tick_params(axis='x', which='both', top='off',length=2)
            plt.tick_params(axis='y', which='both', left='off',length=2)
    
        # now get the tick marks    
        n_target_tics = 4
        xlocs,ylocs,new_x_labels,new_y_labels = raster.format_ticks_for_UTM_imshow(hillshade_header,x_max,x_min,y_max,y_min,n_target_tics)  
        plt.xticks(xlocs, new_x_labels, rotation=60)
        plt.yticks(ylocs, new_y_labels) 
        
        plt.annotate(labels[i-1], xy=(0.92, 0.96), backgroundcolor='white', xycoords='axes fraction', fontsize=10, horizontalalignment='left', verticalalignment='top')
    
        x_center = int(x_max/2.)    
        y_center = int(y_max/2.)    
        
        plt.xlim(x_center-2000,x_center+2000)    
        plt.ylim(y_center+2000,y_center-2000)        
        
    
    fig.text(0.5, 0.02, 'Easting (m)', ha='center', va='center', size=14)
    fig.text(0.02, 0.5, 'Northing (m)', ha='center', va='center', rotation='vertical', size=14)
    
    plt.tight_layout()  
    
    #quarter page = 95*115
    #half page = 190*115 (horizontal) 95*230 (vertical)
    #full page = 190*230
    fig.set_size_inches(mm_to_inch(190), mm_to_inch(200))
        
    plt.savefig('Hillshades.png', dpi = 500)
    return 'Hillshades.png'

def Combine(Outline,Hillshades, trim, OutputName):
    
    from PIL import Image
    
    main = Image.open(Hillshades) 
    outline = Image.open(Outline)
    
    width =  main.size[0]
    total_height = main.size[1]+outline.size[1]
    
    new_size = (width,total_height-trim)
    new_im = Image.new("RGB", new_size)
    new_im.paste(outline,(0,0))
    new_im.paste(main, (0, outline.size[1]-trim))
    
    new_im.save(OutputName,quality=100)
    
    
def Tidy_Up(Outline,Hillshade):
    import os
    
    os.remove(Outline)
    os.remove(Hillshade)
    
    
def Make_The_Figure():
    """
    All filenames and paths to data are modifed here in this wrapper
    """
    Hillshade_files = ['NC_HS.flt','OR_HS.flt','GM_HS.flt','CR2_HS.flt']    
    
    Country_Outline = 'explode_project.shp' 
    State_Borders = 'polygon_project.shp'
    Points = 'points.shp'   
    
    Outline = Draw_Outline(Country_Outline,State_Borders,Points)
    Hillshade = Merge_Hillshades(Hillshade_files)
    
    Combine(Outline,Hillshade,80,'Figure_3_Combined.png')
    
    Tidy_Up(Outline,Hillshade)
    
    
Make_The_Figure()    
    
