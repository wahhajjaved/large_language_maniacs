"""
Bounding regions and bounding boxes.

$Id$
"""
from params import Parameter
from Numeric import *
from base import TopoObject

NYI = "Abstract method not implemented."

class BoundingRegion(TopoObject):
    """
    Abstract bounding region class, for any portion of a 2D plane.

    Only subclasses can be instantiated directly.
    """
    
    def __init__(self,**args):
        super(BoundingRegion,self).__init__(**args)
    def contains(self,x,y):
        raise NYI
    def scale(self,xs,ys):
        raise NYI
    def translate(self,xoff,yoff):
        l,b,r,t = self.aarect().lbrt()
        self._aarect = AARectangle((l+xoff,b+yoff),(r+xoff,t+yoff))
    def rotate(self,theta):
        raise NYI
    def aarect(self):
        raise NYI


class BoundingBox(BoundingRegion):
    """
    A rectangular bounding box defined by two points forming
    an axis-aligned rectangle.

    parameters:

    points = a sequence of two points that define an axis-aligned rectangle.
    """
    def __init__(self,**args):
        self._aarect = AARectangle(*args['points'])
        if 'points' in args:
            del args['points']
        super(BoundingBox,self).__init__(**args)        

    def contains(self,x,y):
        """
        Returns true if the given point is contained within the
        bounding box, where all boundaries of the box are
        considered to be inclusive.
        """
        left,bottom,right,top = self.aarect().lbrt()
        return (left <= x <= right) and (bottom <= y <= top)

    def containsbb_exclusive(self,x):
        """
        Returns true if the given BoundingBox x is contained within the
        bounding box, where at least one of the boundaries of the box has
        to be exclusive.
        """
        left,bottom,right,top = self.aarect().lbrt()
        leftx,bottomx,rightx,topx = x.aarect().lbrt()
        return (left <= leftx) and (bottom <= bottomx) and (right >= rightx) and (top >= topx) and (not ((left == leftx) and (bottom == bottomx) and (right == rightx) and (top == topx)))

    def upperexclusive_contains(self,x,y):
        """
        Returns true if the given point is contained within the
        bounding box, where the right and upper boundaries
        are exclusive, and the left and lower boundaries are
        inclusive.  Useful for tiling a plane into non-overlapping
        regions.
        """
        left,bottom,right,top = self.aarect().lbrt()
        return (left <= x < right) and (bottom <= y < top)

    def aarect(self):
        return self._aarect



class BoundingEllipse(BoundingBox):
    """
    Similar to BoundingBox, but it the region is the ellipse
    inscribed within the rectangle.
    """
    def __init__(self,**args):
        super(BoundingEllipse,self).__init__(**args)
        
    def contains(self,x,y):
        left,bottom,right,top = self.aarect().lbrt()
        xr = (right-left)/2.0
        yr = (top-bottom)/2.0
        xc = left + xr
        yc = bottom + yr

        xd = x-xc
        yd = y-yc

        return (xd**2/xr**2 + yd**2/yr**2) <= 1

class BoundingCircle(BoundingRegion):
    """
    A bounding circle.
    parameters:

    center = a single point (x,y)
    radius = a scalar radius
    """
    radius = Parameter(0.5)
    center = Parameter((0.0,0.0))

    def __init__(self,**args):
        super(BoundingCircle,self).__init__(**args)


    def contains(self,x,y):
        xc,yc = self.center
        xd = x-xc
        yd = y-yc
        return xd*xd + yd*yd <= self.radius*self.radius

    def aarect(self):
        xc,yc = self.center
        r = self.radius
        return AARectangle((xc-r,yc-r),(xc+r,yc+r))

inf = array(1)/0.0
class Unbounded(BoundingRegion):
    def __init__(self,**args):
        super(Unbounded,self).__init__(**args)
    def contains(self,x,y):
        return True
    def scale(self,xs,ys):
        pass
    def translate(self,xoff,yoff):
        pass
    def rotate(self,theta):
        pass
    def aarect(self):
        return AARectangle((-inf,-inf),(inf,inf))


class Intersection(BoundingRegion):
    def __init__(self,*regions,**params):
        super(Intersection,self).__init__(**params)
        self.regions = regions

        bounds = [r.aarect().lbrt() for r in self.regions]
        left = max([l for (l,b,r,t) in bounds])
        bottom = max([b for (l,b,r,t) in bounds])
        right = min([r for (l,b,r,t) in bounds])
        top = min([t for (l,b,r,t) in bounds])

        self.__aarect = AARectangle((left,bottom),(right,top))

    def aarect(self):
        return self.__aarect
    
###################################################
class AARectangle:
    """
    Axis-aligned rectangle class.

    Defines the smallest axis-aligned rectangle that encloses a set of
    points.

    Usage:  aar = AARectangle( (x1,y1),(x2,y2), ... , (xN,yN) )
    """
    __slots__ = ['__left','__bottom','__right','__top']
    def __init__(self,*points):
        self.__top = max([y for x,y in points])
        self.__bottom = min([y for x,y in points])
        self.__left = min([x for x,y in points])
        self.__right = max([x for x,y in points])


    def top(self):
        """
        Return the y-coordinate of the top of the rectangle.
        """
        return self.__top
    def bottom(self):
        """
        Return the y-coordinate of the bottom of the rectangle.
        """
        return self.__bottom
    def left(self):
        """
        Return the x-coordinate of the left side of the rectangle.
        """
        return self.__left
    def right(self):
        """
        Return the x-coordinate of the right side of the rectangle.
        """
        return self.__right
    def lbrt(self):
        """
        Return (left,bottom,right,top) as a tuple
        """
        return (self.__left,
                self.__bottom,
                self.__right,
                self.__top)

    def centroid(self):
        """
        Return the centroid of the rectangle.
        """
        left,bottom,right,top = self.lbrt()
        return (right+left)/2.0,(top+bottom)/2.0
    

    def intersect(self,other):

        l1,b1,r1,t1 = self.lbrt()
        l2,b2,r2,t2 = other.lbrt()

        l = max(l1,l2)
        b = max(b1,b2)
        r = min(r1,r2)
        t = min(t1,t2)

        return AARectangle(points=((l,b),(r,t)))

    def width(self):
        return self.__right - self.__left
    def height(self):
        return self.__top - self.__bottom

    def empty(self):
        l,b,r,t = self.lbrt()
        return (r <= l) or (t <= b)
        
                         
