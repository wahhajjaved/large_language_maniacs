"""
ConnectionField and associated classes.

This module defines some basic classes of objects used to create
simulations of cortical sheets that take input through connection
fields that project from other cortical sheets (or laterally from
themselves).

ConnectionField: Holds a single connection field within a CFProjection.

CFProjection: A set of ConnectionFields mapping from a Sheet into a
ProjectionSheet.

CFSheet: A subclass of ProjectionSheet that provides an interface to
the underlying ConnectionFields in any projection of type CFProjection.

$Id$
"""

__version__ = '$Revision$'

# CEBHACKALERT: some things that need to be cleaned up in this file:
# CFProjection sometimes passes *copies* of objects to the CFs it's creating,
# sometimes it doesn't. Some of ConnectionField's methods change their
# arguments, some don't.  These could lead to confusion and some hard-to-track
# bugs. (Same applies to SharedWeightCFProjection.)


import numpy.oldnumeric as Numeric
from numpy import abs
import copy

import patterngenerator
from patterngenerator import PatternGeneratorParameter
from parameterizedobject import ParameterizedObject
from functionfamilies import OutputFnParameter,IdentityOF
from functionfamilies import LearningFnParameter,Hebbian,IdentityLF
from functionfamilies import ResponseFnParameter,DotProduct
from functionfamilies import CoordinateMapperFnParameter,IdentityMF
from projection import Projection,ProjectionSheet, SheetMask
from parameterclasses import Parameter,Number,BooleanParameter,ClassSelectorParameter,Integer,BooleanParameter
from sheet import Sheet,Slice
from sheetview import UnitView, ProjectionView
from boundingregion import BoundingBox,BoundingRegionParameter



# Specified explicitly when creating weights matrix - required
# for optimized C functions.
weight_type = Numeric.Float32


class NullCFError(ValueError):
    """
    Error thrown when trying to create an empty CF.
    """
    def __init__(self,x,y,input,rows,cols):
        ValueError.__init__(self,"ConnectionField at (%s,%s) (input_sheet=%s) has a zero-sized weights matrix (%s,%s); you may need to supply a larger bounds_template or increase the density of the sheet."%(x,y,input,rows,cols))
    
                 
class ConnectionField(ParameterizedObject):
    """
    A set of weights on one input Sheet.

    Each ConnectionField contributes to the activity of one unit on
    the output sheet, and is normally used as part of a Projection
    including many other ConnectionFields.
    """
    
    x = Number(default=0.0,softbounds=(-1.0,1.0),doc="""
        The x coordinate of the location of the center of this ConnectionField
        on the input Sheet, e.g. for use when determining where the weight matrix
        lines up with the input Sheet matrix.""")
    
    y = Number(default=0.0,softbounds=(-1.0,1.0),doc="""
        The y coordinate of the location of the center of this ConnectionField
        on the input Sheet, e.g. for use when determining where the weight matrix
        lines up with the input Sheet matrix.""")

    # Weights matrix; not yet initialized.
    weights = []

    # Specifies how to get a submatrix from the source sheet that is aligned
    # properly with this weight matrix.  The information is stored as an
    # array for speed of access from optimized C components.
    # CEBALERT: can rename this to 'slice_' now.
    slice_array = []

    _has_norm_total = False

    def __get_norm_total(self):
        """
        Return the stored norm_value, if any, or else the current sum of the weights.
        See the norm_total property for more details.
        """
        # The actual value is cached in _norm_total.
        if self._has_norm_total == True:
            return self._norm_total
        else:
            return abs(self.weights).sum()
            
    def __set_norm_total(self,new_norm_total):
        """
        Set an explicit value to be returned by norm_total.
        See the norm_total property for more details.
        """
        self._has_norm_total = True
        self._norm_total = new_norm_total

    def __del_norm_total(self):
        """
        Delete any cached norm_total that may have been set.
        See the norm_total property for more details.
        """
        self._has_norm_total = False


    # CEBALERT: Accessing norm_total as a property from the C code will probably
    # slow it down; this should be checked.
    # We can remove this ALERT now, right?
    norm_total = property(__get_norm_total,__set_norm_total,__del_norm_total,
        """
        The norm_total property returns a value useful in computing
        a sum-based weight normalization.

        By default, the value returned is simply the current sum of
        the connection weights.  However, another value can be
        substituted by setting norm_total explicitly, and this cached
        value will then be returned instead.

        This mechanism has two main purposes.  First, it allows a
        learning function to cache the sum value for an output
        function to use later without computation, which can result in
        significant time savings.  Second, the extra level of
        indirection allows the sum value to be manipulated before it
        is used, to implement operations like joint normalization
        across corresponding CFs in multiple Projections.

        Apart from such cases, norm_total can be ignored.
        
        Note that every person who uses a class that sets or gets
        norm_total must be very careful to ensure that stale values
        will never be accessed.  A good way to do this is to make sure
        that the value is only set just before it will be used, and
        deleted as soon as it has been accessed.
        
        WARNING: Any c-optimized code can bypass this property and access directly
        _has_norm_total, _norm_total
        
        """)


    # CEBALERT: add some default values
    def __init__(self,x,y,input_sheet,bounds_template,
                 weights_generator,mask_template,
                 output_fn=IdentityOF(),slice_=None,**params):
        """
        Create weights at the specified (x,y) location on the specified input_sheet.
        
        The supplied bounds_template is moved to the specified location,
        then converted to an array, and finally the weights pattern is
        drawn inside by the weights_generator.
        
        The mask_template allows the weights to be limited to being non-zero in a subset 
        of the rectangular weights area.  The actual mask is created by cropping the 
        mask_template by the boundaries of the input_sheet, so that the weights all
        correspond to actual locations in the input sheet.  For instance, if a circular 
        pattern of weights is desired, the mask_template should have a disk-shaped 
        pattern of elements with value 1, surrounded by elements with the value 0.  
        If the CF extends over the edge of the input sheet then the weights will 
        actually be half-moon (or similar) rather than circular. 
        
        Note that bounds_template is assumed to have been initialized correctly
        already (i.e. represents the exact bounds) - see
        CFProjection.initialize_bounds().
        """
        # CEBALERT: maybe an external function is required for
        # initializing the bounds? We need to have correctly setup bounds
        # here, in change_bounds(), and in other places such as CFProjection
        # (where the mask is made). At the moment, the function is in
        # CFProjection.

        super(ConnectionField,self).__init__(**params)

        self.x = x; self.y = y
        self.input_sheet = input_sheet
	self.bounds_template = bounds_template
	
        # Move bounds to correct (x,y) location, and convert to an array
        # CEBALERT: make this clearer by splitting into two functions.
        self.offset_bounds(slice_)
	

        # Now we have to get the right submatrix of the mask (in case
        # it is near an edge)
        r1,r2,c1,c2 =  self.get_slice(slice_)
        m = mask_template[r1:r2,c1:c2]
	
        self.mask = m.astype(weight_type)

        # CEBALERT: might want to do something about a size that's specified
        # (right now the size is assumed to be that of the bounds)
        w = weights_generator(x=self.x,y=self.y,bounds=self.bounds,
                              xdensity=self.input_sheet.xdensity,
                              ydensity=self.input_sheet.ydensity,
                              mask=self.mask)
        
        self.weights = w.astype(weight_type)

        # CEBHACKALERT: the system of masking through multiplication
        # by 0 works for now, while the output_fns are all
        # multiplicative.  But in the long run we need a better way to
        # apply the mask.  The same applies anywhere the mask is used,
        # including in learningfns/.
        # We should investigate the numpy.ma module.
        output_fn(self.weights)        


    ### CEBALERT: there is presumably a better way than this.
    def get_slice(self,slice_=None):
        """
        Return the correct slice for a weights/mask matrix at this
        ConnectionField's location on the sheet (i.e. for getting
        the correct submatrix of the weights or mask in case the
        unit is near the edge of the sheet).
        """
        if not slice_:
            slice_ = Slice(self.bounds_template,self.input_sheet)
            
        sheet_rows,sheet_cols = self.input_sheet.activity.shape

        # get size of weights matrix
        n_rows,n_cols = slice_.shape

        # get slice for the submatrix
        center_row,center_col = self.input_sheet.sheet2matrixidx(self.x,self.y)
        
        c1 = -min(0, center_col-n_cols/2)  # assume odd weight matrix so can use n_cols/2 
        r1 = -min(0, center_row-n_rows/2)  # for top and bottom
        c2 = -max(-n_cols, center_col-sheet_cols-n_cols/2)
        r2 = -max(-n_rows, center_row-sheet_rows-n_rows/2)
        return (r1,r2,c1,c2)
        

    # CEBHACKALERT: assumes the user wants the bounds to be centered
    # about the unit, which might not be true. Same HACKALERT as for
    # CFProjection.initialize_bounds()
    def offset_bounds(self,slice_=None):
        """
        Offset the bounds_template to this cf's location and store the
        result in the 'bounds' attribute.

        Also stores the slice_array for access by C.
	"""
        if not slice_:
            slice_ = Slice(self.bounds_template,self.input_sheet)
        else:
            slice_ = copy.copy(slice_)
               
        # translate to this cf's location
        cf_row,cf_col = self.input_sheet.sheet2matrixidx(self.x,self.y)
        bounds_x,bounds_y=self.bounds_template.centroid()
        b_row,b_col=self.input_sheet.sheet2matrixidx(bounds_x,bounds_y)

        row_offset = cf_row-b_row
        col_offset = cf_col-b_col
        slice_.translate(row_offset,col_offset)

        slice_.crop_to_sheet()

        # weights matrix cannot have a zero-sized dimension (could
        # happen at this stage because of cropping)
        nrows,ncols = slice_.shape
        if nrows<1 or ncols<1:
            raise NullCFError(self.x,self.y,self.input_sheet,nrows,ncols)

        self.bounds = slice_.bounds

        # Also, store the array for direct access by C.
        # Numeric.Int32 is specified explicitly here to avoid having it
        # default to Numeric.Int.  Numeric.Int works on 32-bit platforms,
        # but does not work properly with the optimized C activation and
        # learning functions on 64-bit machines.
        self.slice_array = Numeric.array(tuple(slice_),typecode=Numeric.Int32) 


    def get_input_matrix(self, activity):
        r1,r2,c1,c2 = self.slice_array
        return activity[r1:r2,c1:c2]


    def change_bounds(self, bounds_template, mask_template, output_fn=IdentityOF()):
        """
        Change the bounding box for this ConnectionField.

        bounds_template is assumed to have been initialized
        already (its equivalent slice made odd, and
        snapped to grid - as in __init__() ).
        
        Discards weights or adds new (zero) weights as necessary,
        preserving existing values where possible.

        Currently only supports reducing the size, not increasing, but
        should be extended to support increasing as well.
        """
        # CEBALERT: re-write to allow arbitrary resizing
	self.bounds_template = bounds_template
        or1,or2,oc1,oc2 = self.slice_array

        self.offset_bounds()
        r1,r2,c1,c2 = self.slice_array


        if not (r1 == or1 and r2 == or2 and c1 == oc1 and c2 == oc2):
            self.weights = Numeric.array(self.weights[r1-or1:r2-or1,c1-oc1:c2-oc1],copy=1)

            mr1,mr2,mc1,mc2 = self.get_slice()
            m = mask_template[mr1:mr2,mc1:mc2]
            self.mask = m.astype(weight_type)

            # CEBHACKALERT: see __init__() regarding mask & output fn.
            self.weights *= self.mask
            output_fn(self.weights)
            del self.norm_total


    def change_density(self, new_wt_density):
        """Rescale the weight matrix in place, interpolating or decimating as necessary."""
        raise NotImplementedError



class CFPResponseFn(ParameterizedObject):
    """
    Map an input activity matrix into an output matrix using the CFs
    in a CFProjection.

    Objects in this hierarchy of callable function objects compute a
    response matrix when given an input pattern and a set of
    ConnectionField objects.  Typically used as part of the activation
    function for a neuron, computing activation for one Projection.

    Objects in this class must support being called as a function with
    the arguments specified below, and are assumed to modify the
    activity matrix in place.
    """
    _abstract_class_name = "CFPResponseFn"

    def __call__(self, iterator, input_activity, activity, strength, **params):
        raise NotImplementedError


class CFPRF_Plugin(CFPResponseFn):
    """
    Generic large-scale response function based on a simple single-CF function.

    Applies the single_cf_fn to each CF in turn.  For the default
    single_cf_fn of DotProduct(), does a basic dot product of each CF with the
    corresponding slice of the input array.  This function is likely
    to be slow to run, but it is easy to extend with any arbitrary
    single-CF response function.

    The single_cf_fn must be a function f(X,W) that takes two
    identically shaped matrices X (the input) and W (the
    ConnectionField weights) and computes a scalar activation value
    based on those weights.
    """
    single_cf_fn = ResponseFnParameter(default=DotProduct(),
        doc="Accepts a ResponseFn that will be applied to each CF individually.")
    
    def __call__(self, iterator, input_activity, activity, strength):
        single_cf_fn = self.single_cf_fn
        for cf,r,c in iterator():
           r1,r2,c1,c2 = cf.slice_array
           X = input_activity[r1:r2,c1:c2]
           activity[r,c] = single_cf_fn(X,cf.weights)
        activity *= strength


class CFPResponseFnParameter(ClassSelectorParameter):
    """
    Parameter whose value can be any CFProjectionResponseFunction; i.e., a function
    that uses all the CFs of a CFProjection to transform the input activity
    into an output activity.
    """
    __slots__ = []
    __doc__ = property((lambda self: self.doc))

    def __init__(self,default=CFPRF_Plugin(),**params):
        super(CFPResponseFnParameter,self).__init__(CFPResponseFn,default=default,**params)        


class CFPLearningFn(ParameterizedObject):
    """
    Compute new CFs for a CFProjection based on input and output activity values.

    Objects in this hierarchy of callable function objects compute a
    new set of CFs when given input and output patterns and a set of
    ConnectionField objects.  Used for updating the weights of one
    CFProjection.

    Objects in this class must support being called as a function with
    the arguments specified below.
    """
    _abstract_class_name = "CFPLearningFn"
        

    def constant_sum_connection_rate(self,proj,learning_rate):
	""" 
	Return the learning rate for a single connection assuming that
        the total rate is to be divided evenly among all the units in
        the connection field.
	"""
        return learning_rate/proj.n_units()


    # JABALERT: Should the learning_rate be a parameter of this object instead of an argument?
    def __call__(self, proj, input_activity, output_activity, learning_rate, **params):
        """
        Apply this learning function to the given set of ConnectionFields,
        and input and output activities, using the given learning_rate.
        """
        raise NotImplementedError


class CFPLF_Identity(CFPLearningFn):
    """CFLearningFunction performing no learning."""
    single_cf_fn = LearningFnParameter(default=IdentityLF(),constant=True)
  
    def __call__(self, iterator, input_activity, output_activity, learning_rate, **params):
        pass


class CFPLearningFnParameter(ClassSelectorParameter):
    """
    Parameter whose value can be any CFPLearningFn; i.e., a function
    that uses all the CFs of a CFProjection to transform the input activity
    into an output activity.
    """
    __slots__ = []
    __doc__ = property((lambda self: self.doc))

    def __init__(self,default=CFPLF_Identity(),**params):
        super(CFPLearningFnParameter,self).__init__(CFPLearningFn,default=default,**params)        


class CFPLF_Plugin(CFPLearningFn):
    """CFPLearningFunction applying the specified single_cf_fn to each CF."""
    single_cf_fn = LearningFnParameter(default=Hebbian(),
        doc="Accepts a LearningFn that will be applied to each CF individually.")
    def __call__(self, iterator, input_activity, output_activity, learning_rate, **params):
        """Apply the specified single_cf_fn to every CF."""
	single_connection_learning_rate = self.constant_sum_connection_rate(iterator.proj,learning_rate)
        # avoid evaluating these references each time in the loop
        single_cf_fn = self.single_cf_fn


	for cf,r,c in iterator():
            single_cf_fn(cf.get_input_matrix(input_activity),
                         output_activity[r,c], cf.weights, single_connection_learning_rate)
            # CEBHACKALERT: see ConnectionField.__init__() re. mask & output fn
            cf.weights *= cf.mask                

class CFPOutputFn(ParameterizedObject):
    """
    Type for an object that applies some operation (typically something
    like normalization) to all CFs in a CFProjection for which the specified
    mask (typically the activity at the destination of this projection)
    is nonzero.
    """
    _abstract_class_name = "CFPOutputFn"

    # JABALERT: Shouldn't the mask parameter be dropped now that
    # we can pass in a masked iterator?  A NeighborhoodMask iterator
    # might not be the best choice, but it would be trivial to have one
    # masking out all inactive neurons directly.
    def __call__(self, iterator, mask, **params):
        """Operate on each CF for which the mask is nonzero."""
        raise NotImplementedError


class CFPOF_Plugin(CFPOutputFn):
    """
    Applies the specified single_cf_fn to each CF in the CFProjection
    for which the mask is nonzero.
    """
    single_cf_fn = OutputFnParameter(default=IdentityOF(),
        doc="Accepts an OutputFn that will be applied to each CF individually.")
    
    def __call__(self, iterator, mask, **params):
        """
        Apply the single_cf_fn to each CF for which the mask is nonzero.

        For each CF, the sum of the weights is passed as the current
        value of the norm. Following application of the output
        function, the cf's sum is then set equal to the single_cf_fn's
        norm_value.
        """
        if type(self.single_cf_fn) is not IdentityOF:
            single_cf_fn = self.single_cf_fn
            norm_value = self.single_cf_fn.norm_value                

            for cf,r,c in iterator():
              if (mask[r][c] != 0):
                 single_cf_fn(cf.weights)
                 del cf.norm_total


class CFPOF_Identity(CFPOutputFn):
    """
    CFPOutputFn that leaves the CFs unchanged.

    Must never be changed or subclassed, because it might never
    be called. (I.e., it could simply be tested for and skipped.)
    """
    single_cf_fn = OutputFnParameter(default=IdentityOF(),constant=True)
    
    def __call__(self, iterator, mask, **params):
        pass



class CFPOutputFnParameter(ClassSelectorParameter):
    """
    Parameter whose value can be any CFOutputFn; i.e., a function
    that iterates through all the CFs of a CFProjection and applies
    an output_fn to each.
    """
    __slots__ = []
    __doc__ = property((lambda self: self.doc))

    def __init__(self,default=CFPOF_Plugin(),**params):
        super(CFPOutputFnParameter,self).__init__(CFPOutputFn,default=default,**params)        



                    
class CFProjection(Projection):
    """
    A projection composed of ConnectionFields from a Sheet into a ProjectionSheet.

    CFProjection computes its activity using a response_fn of type
    CFPResponseFn (typically a CF-aware version of mdot) and output_fn 
    (which is typically IdentityOF).  The initial contents of the 
    ConnectionFields mapping from the input Sheet into the target
    ProjectionSheet are controlled by the weights_generator, weights_shape,
    and weights_output_fn parameters, while the location of the
    ConnectionField is controlled by the coord_mapper parameter.

    Any subclass has to implement the interface
    activate(self,input_activity) that computes the response from the
    input and stores it in the activity array.
    """
    response_fn = CFPResponseFnParameter(
        default=CFPRF_Plugin(),
        doc='Function for computing the Projection response to an input pattern.')
    
    cf_type = Parameter(default=ConnectionField,constant=True,
        doc="Type of ConnectionField to use when creating individual CFs.")

    # JPHACKALERT: Not all support for null CFs has been implemented.
    # CF plotting and C-optimized CFPxF_ functions need
    # to be fixed to support null CFs without crashing.    
    allow_null_cfs = BooleanParameter(default=False,
        doc="Whether or not the projection can have entirely empty CFs")
    
    nominal_bounds_template = BoundingRegionParameter(
        default=BoundingBox(radius=0.1),doc="""
        Bounds defining the Sheet area covered by a prototypical ConnectionField.
        The true bounds will differ depending on the density (see initialize_bounds()).""")
    
    weights_generator = PatternGeneratorParameter(
        default=patterngenerator.Constant(),constant=True,
        doc="Generate initial weights values.")

    # JABALERT: Confusing name; change to cf_shape or cf_boundary_shape
    weights_shape = PatternGeneratorParameter(
        default=patterngenerator.Constant(),constant=True,
        doc="Define the shape of the connection fields.")

    # CEBALERT: this is temporary (allows c++ matching in certain
    # cases).  We will allow the user to override the mask size, but
    # by offering a scaling parameter.
    autosize_mask = BooleanParameter(
        default=True,constant=True,hidden=True,doc="""
        Topographica sets the mask size so that it is the same as the connection field's
        size, unless this parameter is False - in which case the user-specified size of
        the weights_shape is used. In normal usage of Topographica, this parameter should
        remain True.""")

    learning_fn = CFPLearningFnParameter(
        default=CFPLF_Plugin(),
        doc='Function for computing changes to the weights based on one activation step.')

    # JABALERT: Shouldn't learning_rate be owned by the learning_fn?
    learning_rate = Number(default=0.0,softbounds=(0,100),doc="""
        Amount of learning at each step for this projection, specified
        in units that are independent of the density of each Sheet.""")

    output_fn  = OutputFnParameter(
        default=IdentityOF(),
        doc='Function applied to the Projection activity after it is computed.')

    weights_output_fn = CFPOutputFnParameter(
        default=CFPOF_Plugin(),
        doc='Function applied to each CF after learning.')

    strength = Number(default=1.0,doc="""
        Global multiplicative scaling applied to the Activity of this Sheet.""")

    min_matrix_radius = Integer(default=1,bounds=(0,None),doc="""
        Enforced minimum for radius of weights matrix.
        The default of 1 gives a minimum matrix of 3x3. 0 would
        allow a 1x1 matrix.""")

    coord_mapper = CoordinateMapperFnParameter(
        default=IdentityMF(),
        doc='Function to map a projected coordinate into the target sheet.')


    # shape property defining the dimension of the _cfs field
    def get_shape(self): return len(self._cfs),len(self._cfs[0])
    cfs_shape = property(get_shape)



    def __init__(self,initialize_cfs=True,**params):
        """
        Initialize the Projection with a set of cf_type objects
        (typically ConnectionFields), each located at the location
        in the source sheet corresponding to the unit in the target
        sheet.

        The nominal_bounds_template specified may be altered. The bounds must
        be fit to the Sheet's matrix, and the weights matrix must
        have odd dimensions. These altered bounds are passed to the
        individual connection fields.

        A mask for the weights matrix is constructed. The shape is
        specified by weights_shape; the size defaults to the size
        of the nominal_bounds_template.
        """
        super(CFProjection,self).__init__(**params)

        # get the actual bounds_template by adjusting a copy of the
        # nominal_bounds_template to ensure an odd slice, and to be
        # cropped to sheet if necessary
        self.bounds_template = self.initialize_bounds(self.nominal_bounds_template)

        slice_ = Slice(self.bounds_template,self.src)

        self.mask_template = self.create_mask_template()

        if initialize_cfs:            
            # set up array of ConnectionFields translated to each x,y in the src sheet
            cflist = []

            # JPALERT: Should we be using a 2D object array here instead of a list of lists?
            # (i.e. self._cfs = numpy.array((rows,cols,dtype=object)
            # This would allow single-call addressing (self._cfs[r,c]), and might
            # be more efficient in other ways, but it might require modification
            # of the optimized CFPOFs and CFPLFs.
            for r,y in enumerate(self.dest.sheet_rows()[::-1]):
                row = []
                for c,x in enumerate(self.dest.sheet_cols()):
                    x_cf,y_cf = self.coord_mapper(x,y)
                    self.debug("Creating CF(%d,%d) from src (%.3f,%.3f) to  dest (%.3f,%.3f)"%(r,c,x_cf,y_cf,x,y))
                    try:
                        row.append(self.cf_type(x_cf,y_cf,
                                                self.src,
                                                copy.copy(self.bounds_template),
                                                self.weights_generator,
                                                copy.copy(self.mask_template), 
                                                output_fn=self.weights_output_fn.single_cf_fn,
                                                slice_=slice_))
                    except NullCFError,e:
                        if self.allow_null_cfs:
                            row.append(None)
                        else:
                            raise
                cflist.append(row)

            self._cfs = cflist

        ### JCALERT! We might want to change the default value of the
        ### input value to self.src.activity; but it fails, raising a
        ### type error. It probably has to be clarified why this is
        ### happening
        self.input_buffer = None
        self.activity = Numeric.array(self.dest.activity)


    def create_mask_template(self):
        """
        """
        # Calculate the size & aspect_ratio of the mask if appropriate;
        # mask size set to be that of the weights matrix
        if hasattr(self.weights_shape, 'size') and self.autosize_mask:
            l,b,r,t = self.bounds_template.lbrt()
            self.weights_shape.size = t-b
            self.weights_shape.aspect_ratio = (r-l)/self.weights_shape.size

        # Center mask to matrixidx center
        center_r,center_c = self.src.sheet2matrixidx(0,0)
        center_x,center_y = self.src.matrixidx2sheet(center_r,center_c)
        
        mask_template = self.weights_shape(x=center_x,y=center_y,
                                           bounds=self.bounds_template,
                                           xdensity=self.src.xdensity,
                                           ydensity=self.src.ydensity)
        # CEBALERT: threshold should be settable by user
        mask_template = Numeric.where(mask_template>=0.5,mask_template,0.0)

        return mask_template
        

    def initialize_bounds(self,original_bounds):
        """
        Return sheet-coordinate bounds that correspond exactly to the slice
        of the sheet which best approximates the specified sheet-coordinate
        bounds.

        The supplied bounds are translated to have a center at the
        center of one of the sheet's units (we arbitrarily use the
        center unit), and then these bounds are converted to a slice
        in such a way that the slice exactly includes all units whose
        centers are within the bounds (see
        SheetCoordinateSystem.bounds2slice()). However, to ensure that
        the bounds are treated symmetrically, we take the right and
        bottom bounds and reflect these about the center of the slice
        (i.e. we take the 'xradius' to be right_col-center_col and the
        'yradius' to be bottom_col-center_row). Hence, if the bounds
        happen to go through units, if the units are included on the
        right and bottom bounds, they will be included on the left and
        top bounds. This ensures that the slice has odd dimensions.

        This slice is converted back to the exactly corresponding
        bounds, and these are returned.
        """
        # don't alter the original_bounds
        bounds = copy.deepcopy(original_bounds)
        
        bounds_xcenter,bounds_ycenter=bounds.centroid()
        sheet_rows,sheet_cols=self.src.shape
        # arbitrary (e.g. could use 0,0) 
        center_row,center_col = sheet_rows/2,sheet_cols/2
        unit_xcenter,unit_ycenter=self.src.matrixidx2sheet(center_row,
                                                           center_col)

        #CEBALERT: to be cleaned up...
        self.center_unitxcenter,self.center_unitycenter = unit_xcenter,unit_ycenter

        bounds.translate(unit_xcenter-bounds_xcenter,
                         unit_ycenter-bounds_ycenter)

        ### CEBALERT: for now, assumes weights are to be centered
        # about each unit, whatever the user specified. This will be
        # changed. See also CF.offset_bounds().
        #
        # Slice will (optionally) perform a more general version
        # of this, so it will not need to appear here.
        weights_slice =  Slice(bounds,self.src)
        r1,r2,c1,c2 = weights_slice

        # use the calculated radius unless it's smaller than the min
        xrad=max(c2-center_col-1,self.min_matrix_radius)
        yrad=max(r2-center_row-1,self.min_matrix_radius)

        r2=center_row+yrad+1
        c2=center_col+xrad+1
        r1=center_row-yrad
        c1=center_col-xrad

        weights_slice._set_slice((r1,r2,c1,c2))
        ### end alert

        ### Checks:
        # (1) user-supplied bounds must lead to a weights matrix of at
        # least 1x1
        rows,cols = weights_slice.shape
        if rows==0 or cols==0:
            raise ValueError("nominal_bounds_template results in a zero-sized weights matrix (%s,%s) for %s - you may need to supply a larger nominal_bounds_template or increase the density of the sheet."%(rows,cols,self.name))
        # (2) weights matrix must be odd (otherwise this method has an error)
        # (The second check should move to a test file.)
        if rows%2!=1 or cols%2!=1:
            raise AssertionError("nominal_bounds_template yielded even-height or even-width weights matrix (%s rows, %s columns) for %s - weights matrix must have odd dimensions."%(rows,cols,self.name))

        return weights_slice.bounds


    def n_units(self):
	"""Return the number of unmasked units in a typical ConnectionField."""      
        ### JCALERT! Right now, we take the number of units at the
        ### center of the cfs matrix.  It would be more reliable to
        ### calculate it directly from the target sheet density and
        ### the weight_bounds.  Example:
        #center_r,center_c = sheet2matrixidx(0,0,bounds,xdensity,ydensity)
        rows,cols=self.cfs_shape
        cf = self._cfs[rows/2][cols/2]
	return len(Numeric.nonzero(Numeric.ravel(cf.mask)))


    def cf(self,r,c):
        """Return the specified ConnectionField"""
        return self._cfs[r][c]


    def get_view(self,sheet_x, sheet_y, timestamp):
        """
        Return a single connection field UnitView, for the unit
        located at sheet coordinate (sheet_x,sheet_y).
        """
	matrix_data = Numeric.zeros(self.src.activity.shape,Numeric.Float)
        (r,c) = self.dest.sheet2matrixidx(sheet_x,sheet_y)
        r1,r2,c1,c2 = self.cf(r,c).slice_array
	matrix_data[r1:r2,c1:c2] = self.cf(r,c).weights
        return UnitView((matrix_data,self.src.bounds),sheet_x,sheet_y,self,timestamp)


    def get_projection_view(self, timestamp):
	"""
	Returns the activity in a single projection
	"""
	matrix_data = Numeric.array(self.activity)
	return ProjectionView((matrix_data,self.dest.bounds),self,timestamp)


    def activate(self,input_activity):
        """Activate using the specified response_fn and output_fn."""
        self.input_buffer = input_activity
        self.activity *=0.0
        self.response_fn(MaskedCFIter(self), input_activity, self.activity, self.strength)
        self.output_fn(MaskedCFIter(self),self.activity)


    def learn(self):
        """
        For a CFProjection, learn consists of calling the learning_fn.
        """
        # Learning is performed if the input_buffer has already been set,
        # i.e. there is an input to the Projection.
        if self.input_buffer != None:
            self.learning_fn(MaskedCFIter(self),self.input_buffer,self.dest.activity,self.learning_rate)


    def apply_learn_output_fn(self,mask):
        self.weights_output_fn(MaskedCFIter(self),mask)


    ### JABALERT: This should be changed into a special __set__ method for
    ### bounds_template, instead of being a separate function.
    def change_bounds(self, nominal_bounds_template):
        """
        Change the bounding box for all of the ConnectionFields in this Projection.

        Calls change_bounds() on each ConnectionField.

	Currently only allows reducing the size, but should be
        extended to allow increasing as well.
        """
        bounds_template = self.initialize_bounds(nominal_bounds_template)

        if not self.bounds_template.containsbb_exclusive(bounds_template):
            if self.bounds_template.containsbb_inclusive(bounds_template):
                self.debug('Initial and final bounds are the same.')
            else:
                self.warning('Unable to change_bounds; currently allows reducing only.')
            return

        # it's ok so we can store the bounds and resize the weights
        self.nominal_bounds_template = nominal_bounds_template
        self.bounds_template = bounds_template

        mask_template = self.create_mask_template()
        
        rows,cols = self.get_shape()
        cfs = self._cfs
        output_fn = self.weights_output_fn.single_cf_fn
        for r in xrange(rows):
            for c in xrange(cols):
                cfs[r][c].change_bounds(copy.copy(bounds_template),
                                        copy.copy(mask_template),
                                        output_fn=output_fn)


    def change_density(self, new_wt_density):
        """
        Rescales the weight matrix in place, interpolating or resampling as needed.
	
	Not yet implemented.
	"""
        raise NotImplementedError



class CFIter(object):
    """
    Iterator to walk through all ConnectionFields of all neurons in
    the destination Sheet of the given CFProjection.
    """
    def __init__(self,cfprojection):
        self.proj = cfprojection    

    def __call__(self):
        rows,cols = self.proj.cfs_shape
        for r in xrange(rows):
            for c in xrange(cols):
                cf = self.proj._cfs[r][c]
                if cf is not None:
                    yield cf,r,c



class MaskedCFIter(CFIter):
    """
    Iterator to walk through the ConnectionFields of all active (i.e.,
    non-masked) neurons in the destination Sheet of the given CFProjection.
    """

    def __init__(self,cfprojection):
        super(MaskedCFIter,self).__init__(cfprojection)
    
    def __call__(self):
        rows,cols = self.proj.cfs_shape

        if isinstance(self.proj.dest.mask,SheetMask):
            mask = self.proj.dest.mask.data
            for r in xrange(rows):
                for c in xrange(cols):
                    cf = self.proj._cfs[r][c]
                    if (cf is not None) and mask[r,c]:
                        yield cf,r,c
        else:
            for r in xrange(rows):
                for c in xrange(cols):
                    cf = self.proj._cfs[r][c]
                    if cf is not None:
                        yield cf,r,c
            


### JABALERT: Should consider eliminating this class, moving its
### methods up to ProjectionSheet, because they may in fact be valid
### for all ProjectionSheets.
###    
class CFSheet(ProjectionSheet):
    """
    A ProjectionSheet providing access to the ConnectionFields in its CFProjections.

    CFSheet is a Sheet built from units indexed by Sheet coordinates
    (x,y).  Each unit can have one or more ConnectionFields on another
    Sheet (via this sheet's CFProjections).  Thus CFSheet is a more
    concrete version of a ProjectionSheet; a ProjectionSheet does not
    require that there be units or weights of any kind.  Unless you
    need access to the underlying ConnectionFields for visualization
    or analysis, CFSheet and ProjectionSheet are interchangeable.
    """

    measure_maps = BooleanParameter(True,doc="""
        Whether to include this Sheet when measuring various maps to create SheetViews.""")

    precedence = Number(0.5)


    def update_unit_view(self,x,y,proj_name=''):
        """
	Creates the list of UnitView objects for a particular unit in this CFSheet.
	(There is one UnitView for each Projection to this CFSheet).

	Each UnitView is then added to the sheet_view_dict of its source sheet.
	It returns the list of all UnitView for the given unit.
	"""     
        for p in self.in_connections:
            if not isinstance(p,CFProjection):
                self.debug("Skipping non-CFProjection "+p.name)
            elif proj_name == '' or p.name==proj_name:
                v = p.get_view(x,y,self.simulation.time())
                src = v.projection.src
                key = ('Weights',v.projection.dest.name,v.projection.name,x,y)
                src.sheet_view_dict[key] = v


    ### JCALERT! This should probably be deleted...
    def release_unit_view(self,x,y):
        self.release_sheet_view(('Weights',x,y))

