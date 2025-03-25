import numpy as np
import plotly
import plotly.plotly as py
from plotly.graph_objs import *

# FIXME: Graph generated shows that as wind speed increases, the angle at which
# it increases ground speed increases past 90deg.  This is clearly incorrect.

def wind_correction(wind, angle):
    '''Takes wind speed and wind - course angle'''
    return np.rad2deg(np.arcsin(wind*np.sin(np.deg2rad(angle))))

def groundspeed(wind, angle):
    '''Takes wind speed and heading - wind angle.
    Returns groundspeed / heading'''
    return np.sqrt(1 + wind**2 - 2 * wind * np.cos(np.deg2rad(angle)))

def groundspeed_for_course(wind, angle):
    '''Takes wind speed and course - wind angle.
    Returns groundspeed / heading'''
    wind *= 0.01
    return groundspeed(wind, angle + wind_correction(wind, angle))


data = Data([
    Contour(
        z = np.fromfunction(groundspeed_for_course, (46, 361)),
        contours=dict(
            #start=0.5,
            #end=1.5,
            #size=.05,
        )
    )
])


layout = Layout(
    title='Ground Speed',
    orientation=-90,
    xaxis=dict(
        autotick=False,
        ticks='outside',
        tick0=0,
        dtick=10
    )
)
fig = Figure(data=data, layout=layout)
plotly.offline.plot(fig)
