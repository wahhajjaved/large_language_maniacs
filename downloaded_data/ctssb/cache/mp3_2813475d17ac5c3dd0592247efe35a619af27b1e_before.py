import logging ; thelog = logging.getLogger('mp3')
thelog.debug('Loading minimage.py')
import numarray
import mp3.cord
import mp3
"""This will preform an arbitrary translation on all of the frames.


"""


class CordTransform(mp3.cord.Cord):
    """
    """
    _move = (0, 0, 0)
    _rotate = (0, 0, 0)

    def init(self):
        self.cord.init()

    def __init__(self, cord, move=None, rotate=None):
        """Set up the transformation object.

        When initializing the transformation object, the keywords
        cord=, move=, and rotate= can be used to set the coordinates,
        translation, and rotation.  See docstring of the
        settransformation method for more information.
        """
        self._move = (0., 0., 0.)
        self._rotate = (0., 0., 0.)
        self.cord = cord
        self.settransformation(move)
        self.settransformation(rotate)
                                                        
    def setcord(self, cordobj):
        self.cord = cord 

    def settransformation(self, move=None, rotate=None):
        """Set the translation and rotation of the system.

        Note: supply these arguments when instantiating the class.
        See the __init__ method.

        The argument move= sets the translation, the argument rotate=
        sets the rotation.  Note that the rotation is applied first,
        then translation.

        The default rotation and/or transformation is (0, 0, 0) (no
        change), and failure to give a value to this function leaves
        the value unchanged (from the default or any previous setting)
        """
        if move != None:
            # if len(move)  != 3:
            #     
            self._move = tuple(move)
        if rotate != None:
            self._rotate = tuple(rotate)

    def gettransformation(self):
        """Return the current settings for rotation and translation.

        Return a tuple containing two tuples: (xxx, yyy).

        xxx is a 3-tuple containing the current value of the translation
        applied to each frame.

        yyy is a 3-tuple containing the current value of the rotation
        applied to each frame.
        
        """
        return (self._move, self._rotate )

    def nextframe(self):
        """Return the next frame.
        """
        frame = self.cord.nextframe()
        # do stuff to the frame
        #mp3.transform_frame_in_place(frame, self.move, self.rotate)
        self._frame = mp3.cordtransform(frame,
                                        move=self._move,
                                        move=self._rotate)
        return self._frame

    def zero_frame(self):
        """Returns to frame zero.
        """
        self.cord.zero_frame()
        
    
    def read_n_frames(self, number):
        """Reads `number' more frames, only printing out the last one.

        """
        self.cord.read_n_frames(number-1)
        return self.nextframe()

    def __getattr__(self, attrname):
        """Wrapper for getting cord attributes.

        This is a wrapper for getting things like self.nframes when you
        don't have to worry about setting them yourself.  Going on the
        hypothesis that most of the time these aren't changed, for
        anything that you haven't defined yourself, it will pass it
        through to self.cord.

        Note that this could be bad in some cases!  But I'll take care
        of them when I find them.
        """
        return self.cord.__dict__[attrname]
        
