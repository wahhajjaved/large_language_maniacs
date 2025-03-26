#  This module provides a parent class for all cords to inheret from.
# It doesn't do any reading, but it can handle writing and such.
#
#


import string, struct
import numarray
import math
import logging ; thelog = logging.getLogger('mp3')
thelog.debug('Loading cord.py')
import mp3.functions

class Cord:

    def __repr__(self):
        return "{{cord object}}"
    def __str__(self):
        return "{{cord object}}"
#
#  General Queries
#

    def nframes(self):
        return self._nframes

    def framen(self):
        return self._framen

    def natoms(self):
        return self._natoms

    def frame(self):
        return self._frame

    def firsttstep(self):
        if hasattr(self, "_firsttstep"):
            return self._firsttstep
        else:  # default value
            return 0
    def dcdtype(self):
        if hasattr(self, "_dcdtype"):
            return self._dcdfreq
        else:  # default value
            return "CORD"
    def dcdfreq(self):
        if hasattr(self, "_dcdfreq"):
            return self._dcdfreq
        else:  # default value
            return 0
    def tstep_size(self):
        if hasattr(self, "_tstep_size"):
            return self._tstep_size
        else:  # default value
            return 0
    def ntsteps(self):
        if hasattr(self, "_ntsteps"):
            return self._ntsteps
        else:  # default value
            return 0
    def block_a(self):
        if hasattr(self, "_block_a"):
            return self._block_a
        else:  # default value
            return 0
    def block_b(self):
        if hasattr(self, "_block_b"):
            return self._block_b
        else:  # default value
            return 0
    def charm_v(self):
        if hasattr(self, "_charm_v"):
            return self._charm_v
        else:  # default value
            return 0
    def title(self):
        # Note: if overriding this method, you should also look at 
        # modifying .settitle() and .appendtitle()
        #        
        if hasattr(self, "_title"):
            return self._title
        else:  # default value
            return "No Title Specified"

    #def info():
    #    """Allows querying of meta-information
    #    """

    def settitle(self, title):
        """Change the title record of this file
        """
        self._title = title
    def appendtitle(self, title):
        if hasattr(self, "_title" ):
            self._title = self._title + title
        else:
            self._title = title

#
#   Some queries to get geometric information.
#


    def aposition(self,i):
        """Return position vector of some atom.
        """
        return self.frame()[i]
        
    def adistance(self, i, j):
        """Return distance between two atoms.

        """
        dist_v = self.frame()[i] - self.frame()[j]
        #print self.frame()
        dist_v = numarray.multiply(dist_v, dist_v)
        dist = dist_v.sum()
        return math.sqrt(dist)
        
        
    def aangle(self, i, center, j):
        """Return the angle between three angles in radians.
        """

        # These functions were taken from mp3.functions.  You would
        # probably want to keep them syncronized in both places.
        _dot = numarray.dot
        _norm = lambda x: math.sqrt(_dot(x,x))

        frame = self.frame()
        disp1 = frame[i] - frame[center]
        disp2 = frame[j] - frame[center]
        return math.acos(_dot(disp1, disp2) / (_norm(disp1) * _norm(disp2)))

    def transform(self, move=None, rotate=None):
        """Transform the current frame.


        Rotate the current frame, store the transformed version and return
        it as well.

        This function takes two three-vectors, given by keyword. Angles,
        of course, are in radians.
    
        ! The frame is rotated before it is translated.  Rotations are
        done in the order x,y,z !
    
        move=(x-translate, y-translate, z-translate)
        rotate=(x-rotate, y-rotate, z-rotate)
    
        Does not rotate in place.
        """
        self._frame = mp3.cordtransform(self.frame(), move=move, rotate=rotate)
        return self._frame

#
#   Iterators
#

    def itercords(self):
        """Iterate over cord-objects.

        This docstring documents both the itercords and iterframes
        methods.
        
        It's probably best to start off with an example:
        >>> for i in C.itercords():
        ...     print i.framen()
        0
        1
        2
        3
        4
        ...

        So, this is just like using
        >>> for element in [0, 1, 2, 3]
        >>>     ...

        It's only(?) useful where you would use "for" somewhere.  If
        you did "for i in C.itercords()", this will call C.nextframe(),
        then run the stuff in the for block with i = the cord-object
        (C).  Note that i here is a dummy variable.  Since i is the
        same thing as C (they point to the same thing, so both have
        their frames advanced), you can equally use C inside the loop,
        or even do "for C in C.itercords()"

        ITERFRAMES

        This operates just like C.itercord(), but the dummy variable
        becomes each frame in sequence.  So you could do

        >>> for frame in C.itercords():
        ...     print frame[0]
        [-13.15221596  -6.29832411   1.11053026]
        [-12.95758438  -6.3849206    1.09611571]
        ... and so on

        Again, note that "frame" is a dummy variable here, and you can
        keep using C inside of the loop.  C.nextframe() is called
        between each loop, so you can get all the standard information,
        such as C.framen(), etc.
        
        """
        for i in range(self.nframes()):
            self.nextframe()
            yield self
    def iterframes(self):
        """Iterate over frames.

        See docstring of the itercords method for an explanation.
        """
        for i in range(self.nframes()):
            self.nextframe()
            yield self.frame()

    
        
##
## Stuff for writing DCDs
##
##

    def writedcd(self, filename):
        """Writes a dcd to a given filename.

        Write an entire DCD to a file at one time.  You will not have
        access to the DCD while writing is commencing.  The cord must
        not have been advanced (as in, you have not called
        .nextframe()).  

        Also see the group of methods documented under writedcd_start.
        """
        fileobject = file(filename, "wb")
        self._writedcd(fileobject)
        fileobject.close()


    def writedcd_start(self, filename, nframes=None):
        """Begin step-by-step DCD writing.

        There may be times when you wish to write out a dcd, but
        modify each frame before writing.  This allows that to be done.

        To begin, call writedcd_start.  The first argument is the file
        you wish to write the DCD to.  The second argument adjusts the
        number of frames written in the header, for example, if you
        don't want to write all of the frames.  Since the DCD format
        encodes nframes in the header, this must be set at the start
        (note: a more advanced method is planned for the future).

        After opening the file with writedcd_start, can begin your
        processing of the coordinates.  You must manually call
        nextframe() (or read_n_frames()) on the object each and every
        time you want new frames.  This does imply that you must call
        nextframe() before you can look at the very first frame.

        To finish writing, use writedcd_stop().  This will close the
        file.

        writedcd_start
        writedcd_nextframe
        writedcd_stop
        """
        # Change nframes if we want to use a different value for writing.
        if nframes != None:
            self.nframes_original = self.nframes
            self.nframes = lambda : nframes

        # Improved plan for nextframes: keep a counter of how many frames
        # have been written.  After writing each frame, go back to the
        # beginning and change nframes.  This makes it a whole lot more
        # transparent.

        self._dcdwritefo = file(filename, "wb")
        self._dcdwritefo.write( self._bindcd_header() )

        # We have to reset nframes to the original value if we changed it!
        if nframes != None:
            self.nframes = self.nframes_original
            del self.nframes_original
    def writedcd_nextframe(self):
        """Write the next frame of a DCD step-by-step.

        Documented under writedcd_start.
        """
        self._dcdwritefo.write( self._bindcd_frame() )
    def writedcd_stop(self):
        """Finish step-by-step DCD writing

        Documented under writedcd_start.
        """
        self._dcdwritefo.close()
        del self._dcdwritefo
    #def writedcd_setnframes(self, nframes):


    def _writedcd(self, outfo):
        """Write a dcd to a file object which has been opened for writing.

        You probably want to use "writedcd" instead.
        """

        thelog.debug('--in cord.py, writedcd()')
        if self.framen() != -1:
            thelog.critical('the dcd should be at frame -1 before you try to print it out')
        outfo.write( self._bindcd_header() )
        for i in range(0,self.nframes() ):
            self.nextframe()
            outfo.write( self._bindcd_frame() )

    
    def _bindcd_header(self):
        """Returns the 3-record binary dcd header."""

        thelog.debug('--in cord.py, bindcd_header()')
        outdata = self._bindcd_firstheader() 
        outdata = outdata + self._bindcd_titlerecord() 
        outdata = outdata + self._bindcd_natomrecord() 
        return outdata

    
    def _bindcd_firstheader(self):
        """Returns the binary first header in the dcd."""
        thelog.debug('--in cord.py, bindcd_firstheader()')
    
        header_format = \
        "i---cccci---i---i---i---xxxxxxxxxxxxxxxxxxxxf---i---i---xxxxxxxxxxxxxxxxxxxxxxxxxxxxi---i---"
        # |1  |5   |10  |15  |20  |25  |30  |35  |40  |45  |50  |55  |60  |65  |70  |75  |80  |85  |90
        #|header size=84                             |tstep_size                             |charm_ver
        #    |CORD=has coordinates                       |block_a                                |header_size=84
        #        |nframes                                    |block_b
        #            |starting timestep
        #                |timestep between coord sets
        #                    |nframes*tstep_size 
        header_format = string.replace(header_format, '-', '')
        outdata = struct.pack(header_format, 84, 'C','O','R','D', self.nframes(), self.firsttstep(), self.dcdfreq(), ( self.dcdfreq()*self.nframes() ) , self.tstep_size(), self.block_a(), self.block_b(), self.charm_v(), 84)
        return outdata
    
    
    def _bindcd_titlerecord(self):
        """Returns the binary title record of the dcd."""

        thelog.debug('--in cord.py, bindcd_titlerecord()')
        title = ""

        #be sure that the title is a multiple of 80 long...
        if len(self.title())%80 == 0:
            title = self.title()
        else:
            title = self.title() + " "*(80 - (len(self.title())%80))

        header_size = len(title) / 80   #this could cause problems very easily if the header got read wrong.
        outdata = struct.pack("i", (80*header_size)+4)
        outdata = outdata + struct.pack("i", header_size)
        outdata = outdata + title
        outdata = outdata + struct.pack("i", (80*header_size)+4)
        return outdata
    
    def _bindcd_natomrecord(self):
        """Returns the dcd's (binary) natoms record."""

        thelog.debug('--in cord.py, bindcd_natomrecord()')
        outdata = struct.pack("i", 4)
        outdata = outdata + struct.pack("i", self.natoms())
        outdata = outdata +  struct.pack("i", 4)
        return outdata
    
    
    def _bindcd_frame(self):
        """Returns a binary (dcd) representation of the frame in self.frame."""
        thelog.debug('--in cord.py, bindcd_frame()')
        frame = self.frame()
        pad = struct.pack('i', 4 * frame.shape[0] )
        the_record = [ pad, frame[:,0].tostring(), pad,
                       pad, frame[:,1].tostring(), pad,
                       pad, frame[:,2].tostring(), pad ]
        outdata = "".join(the_record)
        # outdata =           pad
        # outdata = outdata + frame[:,0].tostring()
        # outdata = outdata + pad + pad
        # outdata = outdata + frame[:,1].tostring()
        # outdata = outdata + pad + pad
        # outdata = outdata + frame[:,2].tostring()
        # outdata = outdata + pad                   
        return outdata                           
                                                 
                                                 
                                                 
