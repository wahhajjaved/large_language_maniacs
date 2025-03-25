"""
The Test Pattern window allows input patterns to be previewed.

$Id$
"""
__version__='$Revision$'

## Notes:
# * need to remove audigen pgs
# * missing disparity flip hack (though see JABHACKALERT below)
# * values like pi are written over
# * need to sort the list of Pattern generators

## Needs to be upgraded to behave how we want:
### JABHACKALERT: Should use PatternPresenter (from
### topo.command.analysis), which will allow flexible support for
### making objects with different parameters in the different eyes,
### e.g. to test ocular dominance or disparity.

# CBENHANCEMENT: add 'use for learning' to install current pattern
# (saving previous ones)?

from Tkinter import Frame

from .. import param
from ..param import tk

import topo

from topo.base.sheetview import SheetView
from topo.base.patterngenerator import PatternGenerator
from topo.sheet.generator import GeneratorSheet
from topo.command.basic import pattern_present, wipe_out_activity
from topo.plotting.plot import make_template_plot
from topo.plotting.plotgroup import SheetPlotGroup
from topo.base.simulation import EPConnectionEvent
from topo.base.sheet import Sheet

from plotgrouppanel import SheetPanel


class TestPatternPlotGroup(SheetPlotGroup):

    def _plot_list(self):
        plot_list = []
        for sheet in self._sheets():
            plot_list.append(self._create_plot(sheet))

        return plot_list
        
    def _create_plot(self,sheet):
        new_view = SheetView((sheet.input_generator(),sheet.bounds),
                              sheet.name,sheet.precedence,topo.sim.time())        
        sheet.sheet_views['Activity']=new_view
        channels = {'Strength':'Activity','Hue':None,'Confidence':None}

        ### JCALERT! it is not good to have to pass '' here... maybe a test in plot would be better
        return make_template_plot(channels,sheet.sheet_views,
                                  sheet.xdensity,sheet.bounds,self.normalize,name='')



class TestPattern(SheetPanel):

    sheet_type = GeneratorSheet
    
    dock = param.Boolean(False)

    edit_sheet = param.ObjectSelector(doc="""Sheet for which to edit pattern properties.""")

    plastic = param.Boolean(default=False,doc="""Whether to enable plasticity during presentation.""")
    duration = param.Number(default=1.0,doc="""How long to run the simulator when presenting.""",
                      softbounds=(0.0,10.0))

    Present = tk.Button(doc="""Present this pattern to the simulation.""")

    pattern_generator = param.ClassSelector(class_=PatternGenerator, doc="""Type of pattern to present. Each type has various parameters that can be changed.""")



    def __init__(self,master,plotgroup=None,**params):
        plotgroup = plotgroup or TestPatternPlotGroup()
        
	super(TestPattern,self).__init__(master,plotgroup,**params)
        
        self.auto_refresh = True

        self.plotcommand_frame.pack_forget()
        for name in ['update_command','plot_command','Fwd','Back']:
            self.hide_param(name)

        edit_sheet_param = self.get_parameter_object('edit_sheet')
        edit_sheet_param.objects = self.plotgroup._sheets()

        self.pg_control_pane = Frame(self) #,bd=1,relief="sunken")
        self.pg_control_pane.pack(side="top",expand='yes',fill='x')
        
        self.params_frame = tk.ParametersFrame(
            self.pg_control_pane,
            parameterized_object=self.pattern_generator,
            on_modify=self.conditional_refresh,
            msg_handler=master.status)

        self.params_frame.hide_param('Close')
        self.params_frame.hide_param('Refresh')

        self.pack_param('edit_sheet',parent=self.pg_control_pane,on_modify=self.switch_sheet)
        self.pack_param('pattern_generator',parent=self.pg_control_pane,
                        on_modify=self.change_pattern_generator,side="top")
        
        present_frame = Frame(self)
        present_frame.pack(side='bottom')

        self.pack_param('plastic',side='bottom',parent=present_frame)
        self.params_frame.pack(side='bottom',expand='yes',fill='x')
        self.pack_param('duration',parent=present_frame,side='left')
        self.pack_param('Present',parent=present_frame,on_change=self.present_pattern,side="right")


    def setup_plotgroup(self):
        super(TestPattern,self).setup_plotgroup()
        
        # CB: could copy the sheets instead (deleting connections etc)
        self.plotgroup.sheets = [GeneratorSheet(name=gs.name,
                                                nominal_bounds=gs.nominal_bounds,
                                                nominal_density=gs.nominal_density)
                                 for gs in topo.sim.objects(GeneratorSheet).values()]
        self.plotgroup._set_name("Test Pattern")


    def switch_sheet(self):
        self.pattern_generator = self.edit_sheet.input_generator
        self.change_pattern_generator()

        
    def change_pattern_generator(self):
        """
        Set the current PatternGenerator to the one selected and get the
        ParametersFrameWithApply to draw the relevant widgets
        """
        self.params_frame.set_PO(self.pattern_generator)

        for sheet in self.plotgroup._sheets():
            if sheet==self.edit_sheet:
                sheet.set_input_generator(self.pattern_generator)
        
        self.conditional_refresh()


    def refresh(self):
        """
        Simply update the plots: skip all handling of history.
        """
        self.refresh_plots()

        
    def present_pattern(self):
        """
        Move the user created patterns into the GeneratorSheets, run for
        the specified length of time, then restore the original
        patterns.
        """
        topo.sim.run(0.0)  # ensure EPs are start()ed
        
        topo.sim.state_push()
        wipe_out_activity()
        topo.sim.event_clear(EPConnectionEvent)
        input_dict = dict([(sheet.name,sheet.input_generator) for sheet in self.plotgroup._sheets()])
        pattern_present(input_dict,self.duration,
                        plastic=self.plastic,overwrite_previous=False)
        topo.guimain.auto_refresh()
        topo.sim.state_pop()
        
