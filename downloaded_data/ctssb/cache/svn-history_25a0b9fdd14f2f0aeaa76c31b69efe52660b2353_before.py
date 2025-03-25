"""
Vision-specific analysis functions.

$Id: featureresponses.py 7714 2008-01-24 16:42:21Z antolikjan $
"""
__version__='$Revision: 7714 $'

from math import fmod,floor,pi,sin,cos,sqrt

import numpy
from numpy.oldnumeric import Float
from numpy import zeros, array, size, empty, object_
#import scipy

try:
    import pylab
except ImportError:
    print "Warning: Could not import matplotlib; pylab plots will not work."

from .. import param

import topo
import topo.command.pylabplots
from topo.base.cf import CFSheet
from topo.base.sheetview import SheetView
from topo.misc.filepath import normalize_path
from topo.misc.numbergenerator import UniformRandom
from topo.plotting.plotgroup import create_plotgroup, plotgroups


max_value = 0
global_index = ()

def _complexity_rec(x,y,index,depth,fm):
        """
        Recurrent helper function for complexity()
        """
        global max_value
        global global_index
        if depth<size(fm.features):
            for i in range(size(fm.features[depth].values)):
                _complexity_rec(x,y,index + (i,),depth+1,fm)
        else:
            if max_value < fm.full_matrix[index][x][y]:
                global_index = index
                max_value = fm.full_matrix[index][x][y]    
    


def complexity(full_matrix):
    global global_index
    global max_value
    """This function expects as an input a object of type FullMatrix which contains
    responses of all neurons in a sheet to stimuly with different varying parameter values.
    One of these parameters (features) has to be phase. In such case it computes the classic
    modulation ratio (see Hawken et al. for definition) for each neuron and returns them as a matrix.
    """
    rows,cols = full_matrix.matrix_shape
    complexity = zeros(full_matrix.matrix_shape)
    complex_matrix = zeros(full_matrix.matrix_shape,object_)
    fftmeasure = zeros(full_matrix.matrix_shape,Float)
    i = 0
    
    for f in full_matrix.features:
        if f.name == "phase":
            
            phase_index = i
            break
        i=i+1
    sum = 0.0
    res = 0.0
    average = 0.0
    for x in range(rows):
        for y in range(cols):
            complex_matrix[x,y] = []#
            max_value=-0.01
            global_index = ()
            _complexity_rec(x,y,(),0,full_matrix)
            
            #compute the sum of the responses over phases given the found index of highest response 

            iindex = array(global_index)
            sum = 0.0
            for i in range(size(full_matrix.features[phase_index].values)):
                iindex[phase_index] = i
                sum = sum + full_matrix.full_matrix[tuple(iindex.tolist())][x][y]
                
            #average
            average = sum / float(size(full_matrix.features[phase_index].values))
            
            res = 0.0
            #compute the sum of absolute values of the responses minus average
            for i in range(size(full_matrix.features[phase_index].values)):
                iindex[phase_index] = i
                res = res + abs(full_matrix.full_matrix[tuple(iindex.tolist())][x][y] - average)
                complex_matrix[x,y] = complex_matrix[x,y] + [full_matrix.full_matrix[tuple(iindex.tolist())][x][y]]
            #this is taking away the DC component
            complex_matrix[x,y] -= numpy.min(complex_matrix[x,y]) 
            complexity[x,y] = res / (2*sum)
            fft = numpy.fft.fft(complex_matrix[x,y]+complex_matrix[x,y]+complex_matrix[x,y]+complex_matrix[x,y],2048)
            first_har = 2048/len(complex_matrix[0,0])
            fftmeasure[x,y] = (2 *abs(fft[first_har]) * abs(fft[first_har]) )/(abs(fft[0]) * abs(fft[0]))
    return fftmeasure

def phase_preference_scatter_plot(sheet_name,diameter=0.39):
    r = UniformRandom(seed=1023)
    preference_map = topo.sim[sheet_name].sheet_views['PhasePreference']
    offset_magnitude = 0.01
    datax = []
    datay = []
    (v,bb) = preference_map.view()
    for z in zeros(300):
        x = r() - 0.5
        y = r() - 0.5
        rand = r()
        xoff = sin(rand*2*pi)*offset_magnitude
        yoff = cos(rand*2*pi)*offset_magnitude
        xx = max(min(x+xoff,diameter),-diameter)
        yy = max(min(y+yoff,diameter),-diameter)
        x = max(min(x,diameter),-diameter)
        y = max(min(y,diameter),-diameter)
        [xc1,yc1] = topo.sim[sheet_name].sheet2matrixidx(xx,yy)
        [xc2,yc2] = topo.sim[sheet_name].sheet2matrixidx(x,y)
        if((xc1==xc2) &  (yc1==yc2)): continue
        datax = datax + [v[xc1,yc1]]
        datay = datay + [v[xc2,yc2]]
    
    for i in range(0,len(datax)):
        datax[i] = datax[i] * 360
        datay[i] = datay[i] * 360
        if(datay[i] > datax[i] + 180): datay[i]=  datay[i]- 360
        if((datax[i] > 180) & (datay[i]> 180)): datax[i] = datax[i] - 360; datay[i] = datay[i] - 360
        if((datax[i] > 180) & (datay[i] < (datax[i]-180))): datax[i] = datax[i] - 360; #datay[i] = datay[i] - 360
        
    f = pylab.figure()
    pylab.plot(datax,datay,'ro')
    pylab.plot([0,360],[-180,180])
    pylab.plot([-180,180],[0,360])
    pylab.plot([-180,-180],[360,360])
    pylab.axis([-180,360,-180,360])
    pylab.grid()
    pylab.savefig(normalize_path(str(topo.sim.timestr()) + sheet_name + "_scatter.png"))



###############################################################################
# JABALERT: Should we move this plot and command to analysis.py or
# pylabplots.py, where all the rest are?
#
# In any case, it requires generalization; it should not be hardcoded
# to any particular map name, and should just do the right thing for
# most networks for which it makes sense.  E.g. it already measures
# the ComplexSelectivity for all measured_sheets, but then
# plot_modulation_ratio only accepts two with specific names.
# plot_modulation_ratio should just plot whatever it is given, and
# then analyze_complexity can simply pass in whatever was measured,
# with the user controlling what is measured using the measure_map
# attribute of each Sheet.  That way the complexity of any sheet could
# be measured, which is what we want.
#
# Specific changes needed:
#   - Make plot_modulation_ratio accept a list of sheets and
#      plot their individual modulation ratios and combined ratio.
#   - Remove complex_sheet_name argument, which is no longer needed
#   - Make sure it still works fine even if V1Simple doesn't exist;
#     as this is just for an optional scatter plot, it's fine to skip
#     it.
#   - Preferably remove the filename argument by default, so that
#     plots will show up in the GUI


def analyze_complexity(full_matrix,simple_sheet_name,complex_sheet_name,filename=None):
    """
    Compute modulation ratio for each neuron, to distinguish complex from simple cells.

    Uses full_matrix data obtained from measure_or_pref().

    If there is a sheet named as specified in simple_sheet_name,
    also plots its phase preference as a scatter plot.
    """
    measured_sheets = [s for s in topo.sim.objects(CFSheet).values()
                       if hasattr(s,'measure_maps') and s.measure_maps]

    for sheet in measured_sheets:   
        complx = array(complexity(full_matrix[sheet]))
        # Should this be renamed to ModulationRatio?
        sheet.sheet_views['ComplexSelectivity']=SheetView((complx,sheet.bounds), sheet.name , sheet.precedence, topo.sim.time())

    topo.command.pylabplots.plot_modulation_ratio(full_matrix,simple_sheet_name=simple_sheet_name,complex_sheet_name=complex_sheet_name,filename=filename)

    # Avoid error if no simple sheet exists
    try:
        phase_preference_scatter_plot(simple_sheet_name,diameter=0.24999)
    except AttributeError:
        print "Skipping phase preference scatter plot; could not analyze region %s." \
              % simple_sheet_name


def measure_and_analyze_complexity():
    """Macro for measuring orientation preference and then analyzing its complexity."""
    from topo.command.analysis import measure_or_pref
    fm = measure_or_pref(frequencies=[3.0],num_orientation=8,scale=0.3,num_phase=32)
    analyze_complexity(fm,simple_sheet_name="V1Simple",complex_sheet_name="V1Complex",filename="ModulationRatio")


pg= create_plotgroup(name='Orientation Preference and Complexity',category="Preference Maps",
             doc='Measure preference for sine grating orientation.',
             update_command=[measure_and_analyze_complexity])
pg.add_plot('Orientation Preference',[('Hue','OrientationPreference')])
pg.add_plot('Orientation Preference&Selectivity',[('Hue','OrientationPreference'),
						   ('Confidence','OrientationSelectivity')])
pg.add_plot('Orientation Selectivity',[('Strength','OrientationSelectivity')])
pg.add_plot('Modulation Ratio',[('Strength','ComplexSelectivity')])
pg.add_plot('Phase Preference',[('Hue','PhasePreference')])
pg.add_static_image('Color Key','topo/command/or_key_white_vert_small.png')


