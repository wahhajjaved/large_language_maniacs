"""
PatternGenerators based on bitmap images stored in files.

$Id$
"""

# PIL Image is imported as PIL because we have our own Image PatternGenerator
import Image as PIL
import ImageOps

from numpy.oldnumeric import array, Float, sum, ravel, ones

from topo.base.boundingregion import BoundingBox
from topo.base.parameterclasses import Number, Parameter, Enumeration, Integer
from topo.base.parameterclasses import DynamicNumber, StringParameter
from topo.base.parameterizedobject import ParameterizedObject
from topo.base.patterngenerator import PatternGenerator
from topo.base.projection import OutputFnParameter
from topo.base.sheetcoords import SheetCoordinateSystem

from topo.outputfns.basic import DivisiveNormalizeLinf,IdentityOF

from topo.misc.filepaths import Filename


class PatternSampler(ParameterizedObject):
    """
    Stores a SheetCoordinateSystem whose activity represents the
    supplied pattern_array, and when called will resample that array
    at the supplied Sheet coordinates according to the supplied
    scaling parameters.

    (x,y) coordinates outside the pattern_array are returned as the
    background value.
    """

    def __init__(self, pattern_array=None, image=None, whole_pattern_output_fn=IdentityOF(), background_value_fn=None):
        """
        Create a SheetCoordinateSystem whose activity is pattern_array
        (where pattern_array is a Numeric array), modified in place by
        whole_pattern_output_fn.

        If supplied, background_value_fn must accept an array and return a scalar.

        """
        super(PatternSampler,self).__init__()

        if pattern_array is not None and image is not None:
            raise ValueError("PatternSampler instances can have a pattern or an image, but not both.")    
        elif pattern_array is not None:
            pass
        elif image is not None:
            pattern_array = array(image.getdata(),Float)
            pattern_array.shape = (image.size[::-1]) # getdata() returns transposed image?
        else:
            raise ValueError("PatternSampler instances must have a pattern or an image.")

        rows,cols = pattern_array.shape

        self.pattern_sheet = SheetCoordinateSystem(xdensity=1.0,ydensity=1.0,
            bounds=BoundingBox(points=((-cols/2.0,-rows/2.0),
                                       ( cols/2.0, rows/2.0))))
        
        whole_pattern_output_fn(pattern_array)
        self.pattern_sheet.activity = pattern_array

        if not background_value_fn:
            self.background_value = 0.0
        else:
            self.background_value = background_value_fn(self.pattern_sheet.activity)
        

    def __call__(self, x, y, sheet_xdensity, sheet_ydensity, scaling, width=1.0, height=1.0):
        """
        Return pixels from the pattern at the given Sheet (x,y) coordinates.

        sheet_density should be the density of the sheet on which the pattern
        is to be drawn.

        scaling determines how the pattern is scaled initially; it can be:
        
        'stretch_to_fit': scale both dimensions of the pattern so they
        would fill a Sheet with bounds=BoundingBox(radius=0.5)
        (disregards the original's aspect ratio).

        'fit_shortest': scale the pattern so that its shortest
        dimension is made to fill the corresponding dimension on a
        Sheet with bounds=BoundingBox(radius=0.5) (maintains the
        original's aspect ratio).

        'fit_longest': scale the pattern so that its longest dimension
        is made to fill the corresponding dimension on a Sheet with
        bounds=BoundingBox(radius=0.5) (maintains the original's
        aspect ratio).

        'original': no scaling is applied; one pixel of the pattern is
        put in one unit of the sheet on which the pattern being
        displayed.

        The pattern is further scaled according to the supplied width and height.
        """
        # create new pattern sample, filled initially with the background value
        pattern_sample = ones(x.shape, Float)*self.background_value

        # if the height or width is zero, there's no pattern to display...
        if width==0 or height==0:
            return pattern_sample

        # scale the supplied coordinates to match the pattern being at density=1
        x*=sheet_xdensity 
        y*=sheet_ydensity
      
        # scale according to initial pattern scaling selected (size_normalization)
        if not scaling=='original':
            self.__apply_size_normalization(x,y,sheet_xdensity,sheet_ydensity,scaling)

        # scale according to user-specified width and height
        x/=width
        y/=height

        # convert the sheet (x,y) coordinates to matrixidx (r,c) ones
        r,c = self.pattern_sheet.sheet2matrixidx_array(x,y)

        # now sample pattern at the (r,c) corresponding to the supplied (x,y)
        pattern_rows,pattern_cols = self.pattern_sheet.activity.shape
        if pattern_rows==0 or pattern_cols==0:
            return pattern_sample
        else:
            # CEBALERT: is there a more Numeric way to do this?
            rows,cols = pattern_sample.shape
            for i in xrange(rows):
                for j in xrange(cols):
                    # indexes outside the pattern are left with the background color
                    if self.pattern_sheet.bounds.contains_exclusive(x[i,j],y[i,j]):
                        pattern_sample[i,j] = self.pattern_sheet.activity[r[i,j],c[i,j]]

        return pattern_sample

    # Added by Tikesh for presenting stereo images; may not be needed anymore
    def get_image_size(self):
        r,c=self.pattern_array.shape
        return r,c

    def __apply_size_normalization(self,x,y,sheet_xdensity,sheet_ydensity,scaling):
        """
        Initial pattern scaling (size_normalization), relative to the
        default retinal dimension of 1.0 in sheet coordinates.

        See __call__ for a description of the various scaling options.
        """
        pattern_rows,pattern_cols = self.pattern_sheet.activity.shape

        # Instead of an if-test, could have a class of this type of
        # function (c.f. OutputFunctions, etc)...
        if scaling=='stretch_to_fit':
            x_sf,y_sf = pattern_cols/sheet_xdensity, pattern_rows/sheet_ydensity
            x*=x_sf; y*=y_sf

        elif scaling=='fit_shortest':
            if pattern_rows<pattern_cols:
                sf = pattern_rows/sheet_ydensity
            else:
                sf = pattern_cols/sheet_xdensity
            x*=sf;y*=sf
            
        elif scaling=='fit_longest':
            if pattern_rows<pattern_cols:
                sf = pattern_cols/sheet_xdensity
            else:
                sf = pattern_rows/sheet_ydensity
            x*=sf;y*=sf

        else:
            raise ValueError("Unknown scaling option",scaling)



from numpy.oldnumeric import sum,ravel
def edge_average(a):
    "Return the mean value around the edge of an array."
    
    if len(ravel(a)) < 2:
        return float(a[0])
    else:
        top_edge = a[0]
        bottom_edge = a[-1]
        left_edge = a[1:-1,0]
        right_edge = a[1:-1,-1]

        edge_sum = sum(top_edge) + sum(bottom_edge) + sum(left_edge) + sum(right_edge)
        num_values = len(top_edge)+len(bottom_edge)+len(left_edge)+len(right_edge)

        return float(edge_sum)/num_values


class FastPatternSampler(ParameterizedObject):
    """
    A fast-n-dirty pattern sampler using Python Imaging Library
    routines.  Currently this sampler doesn't support user-specified
    scaling or cropping but rather simply scales and crops the image
    to fit the given matrix size without distorting the aspect ratio
    of the original picture.
    """
    sampling_method = Integer(default=PIL.NEAREST,doc="""
       Python Imaging Library sampling method for resampling an image.
       Defaults to Image.NEAREST.""")
       
    def __init__(self, pattern=None, image=None, whole_pattern_output_fn=IdentityOF(), background_value_fn=None):
        super(FastPatternSampler,self).__init__()

        if pattern and image:
            raise ValueError("PatternSampler instances can have a pattern or an image, but not both.")    
        elif pattern is not None:
            self.image = PIL.new('L',pattern.shape)
            self.image.putdata(pattern.ravel())
        elif image is not None:
            self.image = image
        else:
            raise ValueError("PatternSampler instances must have a pattern or an image.")

    def __call__(self, x, y, sheet_xdensity, sheet_ydensity, scaling, width=1.0, height=1.0):

        # JPALERT: Right now this ignores all options and just fits the image into given array.
        # It needs to be fleshed out to properly size and crop the
        # image given the options. (maybe this class needs to be
        # redesigned?  The interface to this function is pretty inscrutable.)

        im = ImageOps.fit(self.image,x.shape,self.sampling_method)

        result = array(im.getdata(),dtype=Float)
        result.shape = im.size[::-1]

        return result
        

class GenericImage(PatternGenerator):
    """
    Generic 2D image generator.

    Generates a pattern from a Python Imaging Library image object.
    Subclasses should override the _get_image method to produce the
    image object.

    The background value is calculated as an edge average: see edge_average().
    Black-bordered images therefore have a black background, and
    white-bordered images have a white background. Images with no
    border have a background that is less of a contrast than a white
    or black one.

    At present, rotation, scaling, etc. just resample; it would be nice
    to support some interpolation options as well.
    """

    # JPALERT: I think that this class should be called "Image" and
    # the "Image" class below should be called "FileImage" or
    # something.  That would break backward compatibility, though.
    
    _abstract_class_name = 'GenericImage'
    
    output_fn = OutputFnParameter(default=IdentityOF())
    
    aspect_ratio  = Number(default=1.0,bounds=(0.0,None),
        softbounds=(0.0,2.0),precedence=0.31,doc=
        "Ratio of width to height; size*aspect_ratio gives the width.")

    size  = Number(default=1.0,bounds=(0.0,None),softbounds=(0.0,2.0),
                   precedence=0.30,doc="Height of the image.")
        
    size_normalization = Enumeration(default='fit_shortest',
        available=['fit_shortest','fit_longest','stretch_to_fit','original'],
        precedence=0.95,doc=
        "How to scale the initial image size relative to the default area of 1.0.")

    whole_image_output_fn = OutputFnParameter(default=DivisiveNormalizeLinf(),
        precedence=0.96,doc=
        "Function applied to the whole, original image array (before any cropping).")

    pattern_sampler_type = Parameter(default=PatternSampler, doc="""
       The type of PatternSampler to use to resample/resize the image.""")


    def __setup_pattern_sampler(self):
        """
        If a new filename or whole_image_output_fn is supplied, create a
        PatternSampler based on the image found at filename.        

        The PatternSampler is given the whole image array after it has
        been converted to grayscale.
        """
        self.ps = self.pattern_sampler_type(image=self._image,
                                            whole_pattern_output_fn=self.last_wiof,
                                            background_value_fn=edge_average)


    def function(self,**params):
        xdensity = params.get('xdensity', self.xdensity)
        ydensity = params.get('ydensity', self.ydensity)
        x        = params.get('pattern_x',self.pattern_x)
        y        = params.get('pattern_y',self.pattern_y)
        size_normalization = params.get('scaling',self.size_normalization)

        height = params.get('size',self.size)
        width = (params.get('aspect_ratio',self.aspect_ratio))*height

        whole_image_output_fn = params.get('whole_image_output_fn',self.whole_image_output_fn)

        if self._get_image(params) or whole_image_output_fn != self.last_wiof:
            self.last_wiof = whole_image_output_fn
            self.__setup_pattern_sampler()
        return self.ps(x,y,float(xdensity),float(ydensity),size_normalization,float(width),float(height))


    def _get_image(self,params):
        """
        Get a new image, if necessary.

        If necessary as indicated by the parameters, get a new image,
        assign it to self._image and return True.  If no new image is
        needed, return False.
        """
        raise NotImplementedError


    ### support pickling of PIL.Image

    # CEBALERT: almost identical code to that in topo.plotting.bitmap.Bitmap...
    # CEB: by converting to string and back, we probably incur some speed
    # penalty on copy()ing GenericImages (since __getstate__ and __setstate__ are
    # used for copying, unless __copy__ and __deepcopy__ are defined instead).
    def __getstate__(self):
        """
        Return the object's state (as in the superclass), but replace
        the '_image' attribute's Image with a string representation.
        """
        state = super(GenericImage,self).__getstate__()

        if '_image' in state:
            import StringIO
            f = StringIO.StringIO()
            image = state['_image']
            image.save(f,format=image.format or 'TIFF') # format could be None (we should probably just not save in that case)
            state['_image'] = f.getvalue()
            f.close()

        return state

    def __setstate__(self,state):
        """
        Load the object's state (as in the superclass), but replace
        the '_image' string with an actual Image object.
        """
        if '_image' in state:
            import StringIO
            state['_image'] = PIL.open(StringIO.StringIO(state['_image']))
        super(GenericImage,self).__setstate__(state)




class Image(GenericImage):
    """
    2D Image generator that reads the image from a file.
    
    The image at the supplied filename is converted to grayscale if it
    is not already a grayscale image. See PIL's Image class for
    details of supported image file formats.
    """

    filename = Filename(default='examples/ellen_arthur.pgm',precedence=0.9,doc=
        """
        File path (can be relative to Topographica's base path) to a bitmap image.
        The image can be in any format accepted by PIL, e.g. PNG, JPG, TIFF, or PGM.
        """)

    def __init__(self, **params):
        """
        Create the last_filename and last_wiof attributes, used to hold
        the last filename and last whole_image_output_function.

        This allows reloading an existing image to be avoided.
        """
        super(Image,self).__init__(**params)
        self.last_filename = None
        self.last_wiof = None

    def _get_image(self,params):
        filename = params.get('filename',self.filename)

        if filename!=self.last_filename:
            self.last_filename=filename
            self._image = ImageOps.grayscale(PIL.open(self.filename))
            return True
        else:
            return False



