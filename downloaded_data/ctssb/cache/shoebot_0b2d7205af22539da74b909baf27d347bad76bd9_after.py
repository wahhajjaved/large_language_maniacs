import sys
import cairo
from shoebot import ShoebotError
from shoebot.core import Bot
from shoebot.data import Point, BezierPath, Image
from shoebot import RGB, \
                    HSB, \
                    CORNER, \
                    CENTER, \
                    MOVETO, \
                    RMOVETO, \
                    LINETO, \
                    RLINETO, \
                    CURVETO, \
                    RCURVETO, \
                    ARC, \
                    ELLIPSE, \
                    CLOSE
                    
from math import sin, cos, pi
from math import radians as deg2rad
from types import TupleType

import locale, gettext
APP = 'shoebot'
DIR = sys.prefix + '/share/shoebot/locale'
locale.setlocale(locale.LC_ALL, '')
gettext.bindtextdomain(APP, DIR)
#gettext.bindtextdomain(APP)
gettext.textdomain(APP)
_ = gettext.gettext

class NodeBot(Bot):
    
    NORMAL = "1"
    FORTYFIVE = "2"
    
    CORNER = CORNER
    CENTER = CENTER
    MOVETO = MOVETO
    RMOVETO = RMOVETO
    LINETO = LINETO
    RLINETO = RLINETO
    CURVETO = CURVETO
    RCURVETO = RCURVETO
    ARC = ARC
    ELLIPSE = ELLIPSE # Shoebot, not nodebox 1.x
    CLOSE = CLOSE

    # Default values    
    color_mode = RGB
    color_range = 1

    def __init__(self, canvas, namespace = None):
        Bot.__init__(self, canvas, namespace)
        canvas.mode = CORNER


    #### Drawing

    # Image

    def image(self, path, x, y, width=None, height=None, alpha=1.0, data=None, draw=True, **kwargs):
        '''Draws a image form path, in x,y and resize it to width, height dimensions.
        '''
        return self.Image(path, x, y, width, height, alpha, data, **kwargs)

    def imagesize(self, path):
        img = Image.open(path)
        return img.size

    # Paths

    def rect(self, x, y, width, height, roundness=0.0, draw=True, fill=None, **kwargs):
        path = self.BezierPath(fillcolor=fill, **kwargs)
        path.rect(x, y, width, height, roundness, self.rectmode)
        if draw:
            path.draw()
        return path

    def rectmode(self, mode=None):
        ### TODO
        if mode in (self.CORNER, self.CENTER, self.CORNERS):
            self.rectmode = mode
            return self.rectmode
        elif mode is None:
            return self.rectmode
        else:
            raise ShoebotError(_("rectmode: invalid input"))

    def oval(self, x, y, width, height, draw=True, **kwargs):
        '''Draws an ellipse starting from (x,y) -  ovals and ellipses are not the same'''
        path = self.BezierPath(**kwargs)
        path.ellipse(x, y, width, height)
        if draw:
            path.draw()
        return path

    def ellipse(self, x, y, width, height, draw=True, **kwargs):
        '''Draws an ellipse starting from (x,y)'''
        path = self.BezierPath(**kwargs)
        path.ellipse(x,y,width,height)
        if draw:
            path.draw()
        return path

    def circle(self, x, y, diameter):
        self.ellipse(x, y, diameter, diameter)

    def line(self, x1, y1, x2, y2):
        '''Draws a line from (x1,y1) to (x2,y2)'''
        self.beginpath()
        self.moveto(x1,y1)
        self.lineto(x2,y2)
        self.endpath()

    def arrow(self, x, y, width, type=NORMAL, draw=True):
        '''Draws an arrow.

        Arrows can be two types: NORMAL or FORTYFIVE.
        Taken from Nodebox.
        '''
        if type == self.NORMAL:
            head = width * .4
            tail = width * .2
            self.beginpath()
            self.moveto(x, y)
            self.lineto(x-head, y+head)
            self.lineto(x-head, y+tail)
            self.lineto(x-width, y+tail)
            self.lineto(x-width, y-tail)
            self.lineto(x-head, y-tail)
            self.lineto(x-head, y-head)
            self.lineto(x, y)
            self.endpath()
#            self.fill_and_stroke()
        elif type == self.FORTYFIVE:
            head = .3 
            tail = 1 + head
            self.beginpath()
            self.moveto(x, y)
            self.lineto(x, y+width*(1-head))
            self.lineto(x-width*head, y+width)
            self.lineto(x-width*head, y+width*tail*.4)
            self.lineto(x-width*tail*.6, y+width)
            self.lineto(x-width, y+width*tail*.6)
            self.lineto(x-width*tail*.4, y+width*head)
            self.lineto(x-width, y+width*head)
            self.lineto(x-width*(1-head), y)
            self.lineto(x, y)
            self.endpath(draw)
#            self.fill_and_stroke()
        else:
            raise NameError(_("arrow: available types for arrow() are NORMAL and FORTYFIVE\n"))

    def star(self, startx, starty, points=20, outer=100, inner=50, draw=True):
        '''Draws a star.

        Taken from Nodebox.
        '''
        self.beginpath()
        self.moveto(startx, starty + outer)

        for i in range(1, int(2 * points)):
            angle = i * pi / points
            x = sin(angle)
            y = cos(angle)
            if i % 2:
                radius = inner
            else:
                radius = outer
            x = startx + radius * x
            y = starty + radius * y
            self.lineto(x,y)

        self.endpath(draw)

    def obama(self, x=0, y=0, s=1):
        self.beginpath()
        self.moveto(x+0, y+0)
        self.moveto(x+30.155835*s, y+3.3597362999999998*s)
        self.curveto(x+22.226585999999998*s, y+3.4767912999999999*s, x+17.558824000000001*s, y+11.938165*s, x+17.099542*s, y+19.025210999999999*s)
        self.curveto(x+16.557696*s, y+22.805612999999997*s, x+15.694208*s, y+27.570126999999999*s, x+20.886292999999998*s, y+24.358142999999998*s)
        self.curveto(x+22.063617999999998*s, y+23.262867999999997*s, x+16.210089999999997*s, y+25.217665999999998*s, x+20.032938999999999*s, y+22.868894999999998*s)
        self.curveto(x+25.583684999999999*s, y+23.357593999999999*s, x+22.084018*s, y+16.985720000000001*s, x+18.091563000000001*s, y+19.354975*s)
        self.curveto(x+17.196534*s, y+12.990902999999999*s, x+21.360583000000002*s, y+6.1242342999999995*s, x+28.662463000000002*s, y+7.5544572999999993*s)
        self.curveto(x+38.693815999999998*s, y+5.1428252999999993*s, x+39.505282000000001*s, y+14.898575999999998*s, x+40.712510000000002*s, y+15.298545999999998*s)
        self.curveto(x+41.478746000000001*s, y+17.796257999999998*s, x+38.611923000000004*s, y+17.259235999999998*s, x+41.188965000000003*s, y+20.135055999999999*s)
        self.curveto(x+41.031133000000004*s, y+21.093715*s, x+40.828136000000001*s, y+22.054302999999997*s, x+40.595178000000004*s, y+23.017814999999999*s)
        self.curveto(x+37.462203000000002*s, y+22.218651999999999*s, x+39.577568000000007*s, y+20.442938999999999*s, x+35.418173000000003*s, y+21.627851999999997*s)
        self.curveto(x+33.602451000000002*s, y+19.520005999999999*s, x+26.432436000000003*s, y+20.067235999999998*s, x+32.427879000000004*s, y+19.574813999999996*s)
        self.curveto(x+36.576917000000002*s, y+22.536335999999995*s, x+36.206899000000007*s, y+18.657166999999998*s, x+32.257211000000005*s, y+18.227402999999995*s)
        self.curveto(x+30.574708000000005*s, y+18.213692999999996*s, x+25.753600000000006*s, y+17.080653999999996*s, x+26.102409000000005*s, y+20.064142999999994*s)
        self.curveto(x+26.629214000000005*s, y+23.430944999999994*s, x+38.445660000000004*s, y+20.437210999999994*s, x+31.723868000000003*s, y+22.684509999999996*s)
        self.curveto(x+25.411513000000003*s, y+23.251439999999995*s, x+37.020808000000002*s, y+23.018320999999997*s, x+40.577397000000005*s, y+23.095826999999996*s)
        self.curveto(x+39.397572000000004*s, y+27.939184999999995*s, x+37.394660000000002*s, y+32.818625999999995*s, x+35.748844000000005*s, y+37.477711999999997*s)
        self.curveto(x+33.876538000000004*s, y+37.505711999999995*s, x+40.912494000000002*s, y+27.210657999999995*s, x+33.551462000000008*s, y+28.513852999999997*s)
        self.curveto(x+29.408984000000007*s, y+26.166980999999996*s, x+30.338694000000007*s, y+27.710668999999996*s, x+33.110568000000008*s, y+30.191032999999997*s)
        self.curveto(x+33.542732000000008*s, y+33.300877999999997*s, x+27.883396000000008*s, y+31.263332999999996*s, x+24.356592000000006*s, y+31.595176999999996*s)
        self.curveto(x+26.592705000000006*s, y+31.132081999999997*s, x+32.999869000000004*s, y+26.980728999999997*s, x+25.889071000000005*s, y+28.137995999999998*s)
        self.curveto(x+24.787247000000004*s, y+28.528912999999999*s, x+23.694590000000005*s, y+29.248256999999999*s, x+22.461438000000005*s, y+29.045728999999998*s)
        self.curveto(x+19.269951000000006*s, y+27.610359999999996*s, x+20.894864000000005*s, y+31.648117999999997*s, x+23.304124000000005*s, y+31.790200999999996*s)
        self.curveto(x+23.016163000000006*s, y+31.879840999999995*s, x+22.756522000000004*s, y+31.999426999999997*s, x+22.532552000000006*s, y+32.155418999999995*s)
        self.curveto(x+18.385237000000007*s, y+34.449280999999992*s, x+20.349656000000007*s, y+30.779214999999994*s, x+19.403592000000007*s, y+29.169828999999993*s)
        self.curveto(x+13.060974000000007*s, y+29.491880999999992*s, x+17.907451000000005*s, y+36.572479999999992*s, x+20.239166000000008*s, y+40.144177999999997*s)
        self.curveto(x+18.873123000000007*s, y+37.739430999999996*s, x+18.08608000000001*s, y+32.890574999999998*s, x+19.360926000000006*s, y+33.977977999999993*s)
        self.curveto(x+20.037191000000007*s, y+36.986654999999992*s, x+25.938847000000006*s, y+41.74645499999999*s, x+26.130852000000004*s, y+38.06631999999999*s)
        self.curveto(x+20.628474000000004*s, y+36.782302999999992*s, x+27.449303000000004*s, y+35.551605999999992*s, x+29.746934000000003*s, y+35.648064999999988*s)
        self.curveto(x+30.410632000000003*s, y+33.076153999999988*s, x+19.772083000000002*s, y+38.383369999999985*s, x+23.268567000000004*s, y+33.779412999999991*s)
        self.curveto(x+27.615261000000004*s, y+31.829713999999992*s, x+31.833047000000004*s, y+35.101421999999992*s, x+35.688399000000004*s, y+31.89302799999999*s)
        self.curveto(x+35.013363000000005*s, y+37.811202999999992*s, x+31.504216000000003*s, y+45.616307999999989*s, x+24.125476000000006*s, y+44.718296999999993*s)
        self.curveto(x+19.661164000000007*s, y+41.819234999999992*s, x+21.309011000000005*s, y+48.927480999999993*s, x+14.919938000000005*s, y+51.24616799999999*s)
        self.curveto(x+9.8282387000000053*s, y+53.10291999999999*s, x+5.8473682000000053*s, y+52.883251999999992*s, x+6.0155459000000047*s, y+56.432774999999992*s)
        self.curveto(x+12.987418000000005*s, y+55.93589999999999*s, x+13.997744000000004*s, y+56.35166499999999*s, x+21.252523000000004*s, y+55.912477999999993*s)
        self.curveto(x+20.898605000000003*s, y+53.130379999999995*s, x+19.688185000000004*s, y+41.857771999999997*s, x+23.656133000000004*s, y+47.023085999999992*s)
        self.curveto(x+25.569923000000003*s, y+49.452668999999993*s, x+28.134662000000006*s, y+51.620268999999993*s, x+30.831404000000006*s, y+52.278003999999996*s)
        self.curveto(x+28.088531000000007*s, y+53.314066999999994*s, x+28.752400000000005*s, y+58.240187999999996*s, x+30.522060000000007*s, y+56.199688999999992*s)
        self.curveto(x+26.248979000000006*s, y+52.41766599999999*s, x+40.622643000000011*s, y+60.60644099999999*s, x+34.287476000000005*s, y+53.45876299999999*s)
        self.lineto(x+33.032337000000005*s, y+52.455290999999988*s)
        self.curveto(x+38.130551000000004*s, y+52.222700999999986*s, x+42.570123000000009*s, y+42.380979999999987*s, x+42.152545000000003*s, y+48.047831999999985*s)
        self.curveto(x+43.123448000000003*s, y+54.821857999999985*s, x+40.010563000000005*s, y+56.547931999999989*s, x+47.969558000000006*s, y+56.614551999999989*s)
        self.curveto(x+53.619178000000005*s, y+56.352016999999989*s, x+55.95324500000001*s, y+57.119506999999992*s, x+59.298673000000008*s, y+56.060458999999987*s)
        self.curveto(x+58.382843999999999*s, y+46.073152*s, x+39.067419999999998*s, y+53.375225999999998*s, x+43.301012*s, y+37.764923000000003*s)
        self.curveto(x+43.428455999999997*s, y+31.694825000000002*s, x+54.123880999999997*s, y+29.681982999999999*s, x+50.010494999999999*s, y+22.514310999999999*s)
        self.curveto(x+47.938220999999999*s, y+20.563641000000001*s, x+44.097188000000003*s, y+25.356368*s, x+47.994453*s, y+21.312273999999999*s)
        self.curveto(x+50.682201999999997*s, y+9.7576163000000005*s, x+40.191285999999998*s, y+3.6382382999999998*s, x+30.155835*s, y+3.3597362999999998*s)
        self.moveto(x+20.239166000000001*s, y+40.144177999999997*s)
        self.curveto(x+20.618817*s, y+40.762231*s, x+20.633900000000001*s, y+40.753855999999999*s, x+20.239166000000001*s, y+40.144177999999997*s)
        self.moveto(x+48.335794999999997*s, y+25.116951*s)
        self.curveto(x+52.603257999999997*s, y+28.884436000000001*s, x+42.579355*s, y+36.129815000000001*s, x+44.680596999999999*s, y+27.957156999999999*s)
        self.curveto(x+46.699556999999999*s, y+28.476931999999998*s, x+47.871873000000001*s, y+29.936544999999999*s, x+48.335794999999997*s, y+25.116951*s)
        self.endpath()

    easteregg = obama

    #### Path
    # Path functions taken from Nodebox and modified

    def beginpath(self, x=None, y=None):
        self._path = self.BezierPath()
        if x and y:
            self._path.moveto(x,y)

        # if we have arguments, do a moveto too
        if x is not None and y is not None:
            self._path.moveto(x,y)

    def moveto(self, x, y):
        if self._path is None:
            ## self.beginpath()
            raise ShoebotError, _("No current path. Use beginpath() first.")
        self._path.moveto(x,y)

    def lineto(self, x, y):
        if self._path is None:
            raise ShoebotError, _("No current path. Use beginpath() first.")
        self._path.lineto(x, y)

    def curveto(self, x1, y1, x2, y2, x3, y3):
        if self._path is None:
            raise ShoebotError, _("No current path. Use beginpath() first.")
        self._path.curveto(x1, y1, x2, y2, x3, y3)

    def arc(self, x, y, radius, angle1, angle2):
        if self._path is None:
            raise ShoebotError, _("No current path. Use beginpath() first.")
        self._path.arc(x, y, radius, angle1, angle2)

    def closepath(self):
        if self._path is None:
            raise ShoebotError, _("No current path. Use beginpath() first.")
        if not self._path.closed:
            self._path.closepath()
            self._path.closed = True

    def endpath(self, draw=True):
        if self._path is None:
            raise ShoebotError, _("No current path. Use beginpath() first.")
        if self._autoclosepath:
            self._path.closepath()
        p = self._path
        if draw:
            p.draw()
            self._path = None
        else:
            # keep the transform so we don't lose it
            self._path.transform = cairo.Matrix(*self._canvas.transform)
        return p

    def drawpath(self, path):
        path.draw()

    def drawimage(self, image):
        self.image(image.path, image.x, image.y, data = image.data)

    def autoclosepath(self, close=True):
        self._autoclosepath = close

    def relmoveto(self, x, y):
        '''Move relatively to the last point.'''
        if self._path is None:
            raise ShoebotError, _("No current path. Use beginpath() first.")
        self._path.relmoveto(x,y)

    def rellineto(self, x, y):
        '''Draw a line using relative coordinates.'''
        if self._path is None:
            raise ShoebotError, _("No current path. Use beginpath() first.")
        self._path.rellineto(x,y)

    def relcurveto(self, h1x, h1y, h2x, h2y, x, y):
        '''Draws a curve relatively to the last point.
        '''
        if self._path is None:
            raise ShoebotError, _("No current path. Use beginpath() first.")
        self._path.relcurveto(x,y)

    def findpath(self, points, curvature=1.0):

        """Constructs a path between the given list of points.

        Interpolates the list of points and determines
        a smooth bezier path betweem them.

        The curvature parameter offers some control on
        how separate segments are stitched together:
        from straight angles to smooth curves.
        Curvature is only useful if the path has more than  three points.
        """

        # The list of points consists of Point objects,
        # but it shouldn't crash on something straightforward
        # as someone supplying a list of (x,y)-tuples.

        for i, pt in enumerate(points):
            if type(pt) == TupleType:
                points[i] = Point(pt[0], pt[1])

        if len(points) == 0: return None
        if len(points) == 1:
            path = self.BezierPath(None)
            path.moveto(points[0].x, points[0].y)
            return path
        if len(points) == 2:
            path = self.BezierPath(None)
            path.moveto(points[0].x, points[0].y)
            path.lineto(points[1].x, points[1].y)
            return path

        # Zero curvature means straight lines.

        curvature = max(0, min(1, curvature))
        if curvature == 0:
            path = self.BezierPath(None)
            path.moveto(points[0].x, points[0].y)
            for i in range(len(points)):
                path.lineto(points[i].x, points[i].y)
            return path

        curvature = 4 + (1.0-curvature)*40

        dx = {0: 0, len(points)-1: 0}
        dy = {0: 0, len(points)-1: 0}
        bi = {1: -0.25}
        ax = {1: (points[2].x-points[0].x-dx[0]) / 4}
        ay = {1: (points[2].y-points[0].y-dy[0]) / 4}

        for i in range(2, len(points)-1):
            bi[i] = -1 / (curvature + bi[i-1])
            ax[i] = -(points[i+1].x-points[i-1].x-ax[i-1]) * bi[i]
            ay[i] = -(points[i+1].y-points[i-1].y-ay[i-1]) * bi[i]

        r = range(1, len(points)-1)
        r.reverse()
        for i in r:
            dx[i] = ax[i] + dx[i+1] * bi[i]
            dy[i] = ay[i] + dy[i+1] * bi[i]

        path = self.BezierPath(None)
        path.moveto(points[0].x, points[0].y)
        for i in range(len(points)-1):
            path.curveto(points[i].x + dx[i],
                         points[i].y + dy[i],
                         points[i+1].x - dx[i+1],
                         points[i+1].y - dy[i+1],
                         points[i+1].x,
                         points[i+1].y)

        return path

    #### Transform and utility

    def beginclip(self,path):
        # FIXME: this save should go into Canvas
        ### TODO
        p = self.ClippingPath(path)
        return p


    def endclip(self):
        p = self.EndClip()

    def transform(self, mode = None):
        '''Mode can be CENTER or CORNER'''
        if mode:
            self._canvas.mode = mode
        return self._canvas.mode

    def translate(self, xt, yt, mode = None):
        self._canvas.translate(xt, yt)
        if mode:
            self._canvas.mode = mode

    def rotate(self, degrees=0, radians=0):
        ### TODO change canvas to use radians
        if radians:
            angle = radians
        else:
            angle = deg2rad(degrees)
        self._canvas.rotate(-angle)

    def scale(self, x=1, y=None):
        if not y:
            y = x
        if x == 0:
            # Cairo borks on zero values
            x = 1
        if y == 0:
            y = 1
        self._canvas.scale(x, y)

    def skew(self, x=1, y=0):
        ### TODO bring back transform mixin
        t = self._canvas.transform
        t *= cairo.Matrix(1,0,x,1,0,0)
        t *= cairo.Matrix(1,y,0,1,0,0)
        self._canvas.transform = t

    def push(self):
        self._canvas.push_matrix()

    def pop(self):
        self._canvas.pop_matrix()

    def reset(self):
        self._canvas.reset_transform()

    #### Color

    def outputmode(self):
        '''
        NOT IMPLEMENTED
        '''
        raise NotImplementedError(_("outputmode() isn't implemented yet"))

    def colormode(self, mode=None, crange=None):
        '''Sets the current colormode (can be RGB or HSB) and eventually
        the color range.

        If called without arguments, it returns the current colormode.
        '''
        if mode is not None:
            if mode == "rgb":
                self.color_mode = RGB
            elif mode == "hsb":
                self.color_mode = HSB
            else:
                raise NameError, _("Only RGB and HSB colormodes are supported.")
        if crange is not None:
            self.color_range = crange
        return self.color_mode

    def colorrange(self, crange):
        self.color_range = float(crange)

    def fill(self,*args):
        '''Sets a fill color, applying it to new paths.'''
        self._canvas.fillcolor = self.color(*args)
        return self._canvas.fillcolor

    def nofill(self):
        ''' Stop applying fills to new paths.'''
        self._canvas.fillcolor = None

    def stroke(self,*args):
        '''Set a stroke color, applying it to new paths.'''
        self._canvas.strokecolor = self.color(*args)
        return self._canvas.strokecolor

    def nostroke(self):
        ''' Stop applying strokes to new paths.'''
        self._canvas.strokecolor = None

    def strokewidth(self, w=None):
        '''Set the stroke width.'''
        if w is not None:
            self._canvas.strokewidth = w
        else:
            return self._canvas.strokewidth

    def background(self,*args):
        '''Set the background colour.'''
        self._canvas.background = self.color(*args)

    #### Text

    def font(self, fontpath=None, fontsize=None):
        '''Set the font to be used with new text instances.

        Accepts TrueType and OpenType files. Depends on FreeType being
        installed.'''
        if fontpath is not None:
            self._fontfile = fontpath
        else:
            return self._fontfile
        if fontsize is not None:
            self._canvas.fontsize = fontsize

    def fontsize(self, fontsize=None):
        if fontsize is not None:
            self._canvas.fontsize = fontsize
        else:
            return self._canvas.fontsize

    def text(self, txt, x, y, width=None, height=1000000, outline=False, draw=True, **kwargs):
        '''
        Draws a string of text according to current font settings.
        '''
        txt = self.Text(txt, x, y, width, height, outline=outline, ctx=None, **kwargs)
        if outline:
          path = txt.path
          if draw:
              path.draw()
          return path
        else:
          return txt

    def textpath(self, txt, x, y, width=None, height=1000000, draw=False, **kwargs):
        '''
        Draws an outlined path of the input text
        '''
        txt = self.Text(txt, x, y, width, height, **kwargs)
        path = txt.path
        if draw:
            path.draw()
        return path

    def textmetrics(self, txt, width=None, height=None, **kwargs):
        '''Returns the width and height of a string of text as a tuple
        (according to current font settings).
        '''
        # for now only returns width and height (as per Nodebox behaviour)
        # but maybe we could use the other data from cairo
        txt = self.Text(txt, 0, 0, width, height, **kwargs)
        return txt.metrics

    def textwidth(self, txt, width=None):
        '''Returns the width of a string of text according to the current
        font settings.
        '''
        w = width
        return self.textmetrics(txt, width=w)[0]

    def textheight(self, txt, width=None):
        '''Returns the height of a string of text according to the current
        font settings.
        '''
        w = width
        return self.textmetrics(txt, width=w)[1]


    def lineheight(self, height=None):
        if height is not None:
            self.canvas._lineheight = height

    def align(self, align="LEFT"):
        self._canvas.align=align

    # TODO: Set the framework to setup font options

    def fontoptions(self, hintstyle=None, hintmetrics=None, subpixelorder=None, antialias=None):
        raise NotImplementedError(_("fontoptions() isn't implemented yet"))

    def autotext(self, sourceFile):
        k = KantGenerator(sourceFile)
        return k.output()


