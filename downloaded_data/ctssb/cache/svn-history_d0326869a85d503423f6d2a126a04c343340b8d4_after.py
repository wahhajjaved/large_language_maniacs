"""
PlotgroupPanels for displaying ProjectionSheet plotgroups.

$Id$
"""
__version__='$Revision$'


# CEBERRORALERT: I've (temporarily) broken most of the buttons like
# normalize and sheet_coords...will be fixed when I clean up all the
# update methods.



import ImageTk
### JCALERT! Try not to have to use chain and delete this import.
from itertools import chain
from Tkinter import Canvas, FLAT 

import topo

from topo.base.cf import CFSheet, CFProjection
from topo.base.projection import ProjectionSheet
from topo.base.parameterclasses import BooleanParameter

from topo.plotting.plotgroup import CFProjectionPlotGroup,ProjectionSheetPlotGroup,CFPlotGroup,ProjectionActivityPlotGroup,ConnectionFieldsPlotGroup

from templateplotgrouppanel import TemplatePlotGroupPanel


### JCALERT! See if we could delete this import * and replace it...
#from topo.commands.analysis import *


def cmp_projections(p1,p2):
    """
    Comparison function for Plots.
    It compares the precedence number first and then the src_name and name attributes.
    """
    if p1.src.precedence != p2.src.precedence:
	return cmp(p1.src.precedence,p2.src.precedence)
    else:
	return cmp(p1,p2)


UNIT_PADDING = 1
BORDERWIDTH = 1

# JDALERT: The canvas creation, border placement, and image
# positioning of Tkinter is very fragile.  This value boosts the size
# of the canvas that the plot image is displayed on.  Too large and
# the border will not be close, too small, and some of the image is
# not displayed.
CANVASBUFFER = 1


# need some refreshing when changing params?

class ProjectionSheetPGPanel(TemplatePlotGroupPanel):
    """
    Abstract base class for panels relating to ProjectionSheets.
    """
    _abstract_class_name = "ProjectionSheetPGPanel"

    plotgroup_type = ProjectionSheetPlotGroup
    sheet_type = ProjectionSheet

    auto_refresh = BooleanParameter(False) # these panels can be slow to refresh

    # CEBHACKALERT: valid_context() needs to be more specific in
    # subclasses.  How to allow valid_context() to work for more
    # specific subclasses (e.g. to replace ProjectionSheet with
    # CFSheet)?
    @staticmethod
    def valid_context():
        """
        Return True if there are Projections in the simulation.

        Used by TopoConsole to determine whether or not to open a ProjectionPanel.
        """
        sheets = topo.sim.objects(ProjectionSheet).values()
        if not sheets:
            return False
        projectionlists=[sheet.in_connections for sheet in sheets]
        projections=[i for i in chain(*projectionlists)]
        return (not projections == [])


    def __init__(self,console,master,pgt,**params):
        super(ProjectionSheetPGPanel,self).__init__(console,master,pgt,**params)
        self.pack_param('sheet',parent=self.control_frame_3,on_modify=self.sheet_change)


    def generate_plotgroup(self):
        p = self.plotgroup_type(template=self.pgt)
        self.populate_sheet_param(p)
        return p


    def sheet_change(self):
        self.refresh()         

        
    def populate_sheet_param(self,p):
        sheets = topo.sim.objects(self.sheet_type).values() 
        sheets.sort(lambda x, y: cmp(-x.precedence,-y.precedence))
        p.params()['sheet'].Arange = sheets
        p.sheet = sheets[0]




class ProjectionActivityPanel(ProjectionSheetPGPanel):

    plotgroup_type = ProjectionActivityPlotGroup
    
    
    def __init__(self,console,master,pgt,**params):       
        super(ProjectionActivityPanel,self).__init__(console,master,pgt,**params)
        self.auto_refresh = True
        # CB: why do we do this?
	self.plotgroup_label='ProjectionActivity'
	

    # CEBALERT! Dynamic info doesn't work on projection activity windows!
    # e.g. on hierarchical there is an error, on cfsom the dynamic info stops
    # half way across the plot...
    # So, dynamic info is disabled for now in proj. act. windows.
    # This will be easier to fix when the class hierarchy is cleaned up
    # (if it is still a problem then).
    def _update_dynamic_info(self,e):
        self.messageBar.message('state',"")

    def _plot_title(self):
        return "Activity in Projections to %s at time %s"%(self.plotgroup.sheet.name,self.plotgroup.time)

   


class CFPGPanel(ProjectionSheetPGPanel):
    """
    Special type of ProjectionSheetPGPanel that supports a situate button.
    """

    sheet_type = CFSheet
    plotgroup_type = CFPlotGroup
    _abstract_class_name = "CFPGPanel"

    def __init__(self,console,master,pgt,**params):
        super(CFPGPanel,self).__init__(console,master,pgt,**params)
        self.pack_param('situate',parent=self.control_frame_3,on_change=self.situate_change)

    def situate_change(self):
        if self.situate:
            self.plotgroup.initial_plot=True
            self.plotgroup.height_of_tallest_plot = 1
        self.redraw_plots()



# CEBHACKALERT: various parts of the dynamic info/right-click menu stuff
# don't make sense at the moment when things like 'situate' are clicked.
class ConnectionFieldsPanel(CFPGPanel):

    plotgroup_type = ConnectionFieldsPlotGroup

    def __init__(self,console,master,pgt,**params):
        self.initial_args=params # CEBALERT: store the initial arguments so we can get sheet,x,y in
                                 # sheet_change if any of them were specified. Isn't there a cleaner
                                 # way?
        super(ConnectionFieldsPanel,self).__init__(console,master,pgt,**params)
        self.pack_param('x',parent=self.control_frame_3,on_change=self.make_plots)
        self.pack_param('y',parent=self.control_frame_3,on_change=self.make_plots)




##############################################################################
        # CEBALERT:
        # - Need to couple taggedslider to a Number parameter in a better way
        # somewhere else.
        # - Clean up or document: passing the params, setting the bounds
        # 
        # Also:        
        # e.g. bound on parameter is 0.5 but means <0.5, taggedslider
        #   still lets you set to 0.5 -> error
            
    def sheet_change(self):
        # CEBHACKALERT: get an inconsequential but scary
        # cf-out-of-range error if you e.g. set y < -0.4 on sheet V1
        # and then change to V2 (which has smaller bounds).
        # x and y don't seem to be updated in time...
        #self.x,self.y = 0.0,0.0

        # CEBALERT: need to crop x,y (for e.g. going to smaller sheet) rather
        # than set to 0
    
        if 'sheet' in self.initial_args: self.sheet=self.initial_args['sheet']

        for coord in ['x','y']:
            self._tk_vars[coord].set(self.initial_args.get(coord,0.0))
          
        l,b,r,t = self.sheet.bounds.lbrt()
        bounds = {'x':(l,r),
                  'y':(b,t)}

        for coord in ['x','y']:
            param_obj=self.get_parameter_object(coord)                
            param_obj.bounds = bounds[coord]
            
            # (method can be called before x,y widgets added)
            if coord in self.representations:
                w=self.representations[coord]['widget']
                w.set_bounds(*param_obj.bounds)
                w.refresh()

        self.initial_args = {} # reset now we've used them
        super(ConnectionFieldsPanel,self).sheet_change()
##############################################################################


    def _plot_title(self):
        return 'Connection Fields of ' + self.sheet.name + \
               ' unit (' + str(self.plotgroup.x) + ',' + str(self.plotgroup.y) + ') at time '\
               + str(self.plotgroup.time)



# CBERRORALERT: when 'Refresh' button is pressed, the current projection is reset to the original.
# Needs to keep the user's selection. Might also happen for other SelectorParameters: need to check.
class CFProjectionPGPanel(CFPGPanel):
    """
    Panel for displaying CFProjections.
    """

    plotgroup_type = CFProjectionPlotGroup

    def __init__(self,console,master,pgt,**params):
        super(CFProjectionPGPanel,self).__init__(console,master,pgt,**params)
        self.pack_param('projection',parent=self.control_frame_3,on_change=self.make_plots)
        self.pack_param('density',parent=self.control_frame_3)


    def generate_plotgroup(self):
        p = super(CFProjectionPGPanel,self).generate_plotgroup()        
        self.populate_projection_param(p)
        return p


    def _plot_title(self):
        return 'Projection ' + self.projection.name + ' from ' + self.projection.src.name + ' to ' \
               + self.sheet.name + ' at time ' + str(self.plotgroup.time)

    def sheet_change(self):
        self.refresh_projections()


    def populate_projection_param(self,p):
        prjns = p.sheet.projections().values() 
        prjns.sort(cmp_projections)
        p.params()['projection'].Arange = prjns
        p.projection = prjns[0]        

    # CEBALERT: here and for other such lists, make things get sorted by precedence.
    def refresh_projections(self):
        self.populate_projection_param(self.plotgroup)

        #################
        # CEBALERT: How do you change list of tkinter.optionmenu options? Use pmw's optionmenu?
        # Or search the web for a way to alter the list in the tkinter one.
        # Currently, replace widget completely: looks bad and is complex.
        # When fixing, remove try/except marked by the 'for projectionpanel' CEBALERT in
        # tkparameterizedobject.py
        if 'projection' in self.representations:
            w  = self.representations['projection']['widget']
            l  = self.representations['projection']['label']
            l.destroy()
            w.destroy()
            self.pack_param('projection',parent=self.representations['projection']['frame'])
        #################


    def display_plots(self):
        """
        CFProjectionPanel requires a 2D grid of plots.
        """
        plots=self.plotgroup.plots
        # Generate the zoomed images.
        self.zoomed_images = [ImageTk.PhotoImage(p.bitmap.image)
                              for p in plots]
        old_canvases = self.canvases

        self.canvases = [Canvas(self.plot_frame,
                           width=image.width()+BORDERWIDTH*2+CANVASBUFFER,
                           height=image.height()+BORDERWIDTH*2+CANVASBUFFER,
                           bd=0)
                         for image in self.zoomed_images]

        # Lay out images
        for i,image,canvas in zip(range(len(self.zoomed_images)),
                                  self.zoomed_images,self.canvases):
            canvas.grid(row=i//self.plotgroup.proj_plotting_shape[0],
                        column=i%self.plotgroup.proj_plotting_shape[1],
                        padx=UNIT_PADDING,pady=UNIT_PADDING)
            # BORDERWIDTH is added because the border is drawn on the
            # canvas, overwriting anything underneath it.
            # The +1 is necessary since the TKinter Canvas object
            # has a problem with axis alignment, and 1 produces
            # the best result.
            canvas.create_image(image.width()/2+BORDERWIDTH+1,
                                image.height()/2+BORDERWIDTH+1,
                                image=image)
            canvas.config(highlightthickness=0,borderwidth=0,relief=FLAT)
            canvas.create_rectangle(1, 1, image.width()+BORDERWIDTH*2,
                                    image.height()+BORDERWIDTH*2,
                                    width=BORDERWIDTH,outline="black")


        # Delete old ones.  This may resize the grid.
        for c in old_canvases:
            c.grid_forget()

        self.sizeright()
    

    def display_labels(self):
        """
        Do not display a label for each plot.
        """
        pass
            




