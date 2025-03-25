import os, sys
import struct
import math
from ctypes import cdll, c_ulonglong, Structure, c_int, c_float

__all__ = ['outline']


base = os.path.dirname(__file__)
sofile = os.path.join(base, '_render_outline.so')
try:
    cfuncs = cdll.LoadLibrary(sofile)
except OSError:
    print('could not import %s'%sofile)
    cfuncs = None
    
class _RenderSettings(Structure):
    _fields_ = [
        ("border_width", c_int),
        ("max_strength", c_int),
        ("rel_strength", c_float),
        ("illum_x", c_float),
        ("illum_y", c_float),
    ]
    
    
if cfuncs:
    def outline(qimage, border_width=None, illum_angle=0, rel_strength=.015, max_strength=144):
        '''add piece outline to the given qimage.
        border_width gives a relative scale for the border. Leave at None to auto-set.
        illum_angle is the angle where the light comes from in degrees, 0=up, clockwise.
        rel_strength gives the relative boldness of the border.
        max_strength gives the maximum brightening/darkening of pixel values.
        '''
        imgptr = qimage.bits()
        w, h = qimage.width(), qimage.height()
        if not border_width:
            border_width = max(w, h)/20
            
        illum_x = math.sin(illum_angle*math.pi/180.)
        illum_y = -math.cos(illum_angle*math.pi/180.)
            
        settings = _RenderSettings(int(border_width), max_strength, rel_strength, illum_x, illum_y)
        cfuncs.outline(c_ulonglong(imgptr), c_int(w), c_int(h), settings)
else:
    def outline(*args, **kwargs):
        pass