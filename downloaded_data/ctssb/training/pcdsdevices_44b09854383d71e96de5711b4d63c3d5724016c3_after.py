#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Profile Intensity Monitor Classes

This script contains all the classes relating to the profile intensity monitor
classes at the user level. A PIM will usually have at least a motor to control
yag position and a camera to view the yag. Additional motors to adjust focus and
zoom can also be included as in the case of the PIMs in the FEE.

Classes Implemented here are as follows:

PIMPulnixDetector
	Pulnix detector with only the plugins used by the PIMs.

PIMMotor
	Profile intensity monitor motor that moves the yag and diode into and out of
	the beam.

PIM
	High level profile intensity monitor class that inherits from PIMMotor and
	has a PIMPulnixDetector as a component.

PIMFee
	High level profile inensity monitor class that is used in the fee. It has
	three IMS motors to control zoom, focus and the position of the yag in
	addition to a FeeOpalDetector as the detector.
"""

############
# Standard #
############
import logging

###############
# Third Party #
###############
import numpy as np
from ophyd.utils.epics_pvs import raise_if_disconnected

##########
# Module #
##########
from .device import Device
from .imsmotor import ImsMotor
from .iocdevice import IocDevice
from .state import statesrecord_class
from ophyd.status import wait as status_wait
from .signal import (EpicsSignal, EpicsSignalRO)
from .component import (Component, FormattedComponent)
from .areadetector.detectors import (PulnixDetector, FeeOpalDetector)
from .areadetector.plugins import (ImagePlugin, StatsPlugin, ProcessPlugin)
from ..utils.pyutils import isnumber

logger = logging.getLogger(__name__)

PIMStates = statesrecord_class("PIMStates", ":OUT", ":YAG", ":DIODE")


class PIMPulnixDetector(PulnixDetector):
    """
    Pulnix detector that is used in the PIM. Plugins should be added on an as
    needed basis here.

    Components
    ----------
    proc1 : ProcessPlugin, ":Proc1:"
    	Plugin component corresponding to Proc1 plugin in AD

    image1 : ImagePlugin, ":IMAGE1:"
    	Plugin component corresponding to image1 plugin in AD

    image2 : ImagePlugin, ":IMAGE2:"
    	Plugin component corresponding to image2 plugin in AD

    stats1 : StatsPlugin, ":Stats1:"
    	Plugin component corresponding to stats1 plugin in AD

    stats2 : StatsPlugin, ":Stats2:"
    	Plugin component corresponding to stats2 plugin in AD    
    """
    proc1 = Component(ProcessPlugin, ":Proc1:", read_attrs=['num_filter'])
    image1 = Component(ImagePlugin, ":IMAGE1:", read_attrs=['array_data'])
    image2 = Component(ImagePlugin, ":IMAGE2:", read_attrs=['array_data'])
    stats1 = Component(StatsPlugin, ":Stats1:", read_attrs=['centroid',
                                                            'mean_value'])
    stats2 = Component(StatsPlugin, ":Stats2:", read_attrs=['centroid',
                                                            'mean_value'])

    def check_camera(self):
        """
        Checks if the camera is acquiring images.

        Raises
        ------
        NotAcquiringError
        	Error raised if called when the camera is not acquiring
        """
        if not self.acquiring:
            raise NotAcquiringError

    @property
    @raise_if_disconnected
    def image(self):
        """
        Returns the image stream reshaped to be the correct size using the size
        component in cam.

        Returns
        -------
        image : np.ndarray
        	Image array
        """
        return np.reshape(np.array(self.image2.array_data.value),
                          (self.cam.size.size_y.value,
                           self.cam.size.size_x.value))
    
    @property
    @raise_if_disconnected
    def acquiring(self):
        """
        Checks to see if the camera is currently acquiring images. Alias for
        cam.acquire

        Returns
        -------
        acquiring : bool
        """
        return bool(self.cam.acquire.value)

    @acquiring.setter
    def acquiring(self, val):
        """
        Setter for acquiring.

        Returns
        -------
        status : StatusObject
        """
        return self.cam.acquire.set(bool(val))

    @property
    @raise_if_disconnected
    def centroid_x(self):
        """
        Returns the beam centroid in x. Alias for stats2.centroids.x.

        Returns
        -------
        centroid_x : float
        	Centroid of the image in x.

        Raises
        ------
        NotAcquiringError
        	When this property is called but the camera isn't acquiring.
        """
        # Make sure the camera is acquiring
        self.check_camera()
        return self.stats2.centroid.x.value

    @property
    @raise_if_disconnected
    def centroid_y(self):
        """
        Returns the beam centroid in y. Alias for stats2.centroids.y.

        Returns
        -------
        centroid_y : float
        	Centroid of the image in y.

        Raises
        ------
        NotAcquiringError
        	When this property is called but the camera isn't acquiring.        
        """
        self.check_camera()
        return self.stats2.centroid.y.value

    @property
    def centroid(self):
        """
        Returns the beam centroid in x and y. Alias for (centroid_x, centroid_y)

        Returns
        -------
        centroids : tuple
        	Tuple of the centroids in x and y

        Raises
        ------
        NotAcquiringError
        	When this property is called but the camera isn't acquiring.                
        """
        return (self.centroid_x, self.centroid_y)
        

class PIMMotor(Device):
    """
    Standard position monitor motor that can move the stage to insert the yag or
    diode, or retract it from the beam path.

    Components
    ----------
    states : PIMStates
    	States component that handles all the motor states.

    Parameters
    ----------
    prefix : str
        The EPICS base of the motor

    read_attrs : sequence of attribute names, optional
        The signals to be read during data acquisition (i.e., in read() and
        describe() calls)

    configuration_attrs : sequence of attribute names, optional
        The signals to be returned when asked for the motor configuration (i.e.
        in read_configuration(), and describe_configuration() calls)

    name : str, optional
        The name of the offset mirror    
    """
    states = Component(PIMStates, "")

    def move_in(self, wait=True, **kwargs):
        """
        Move the PIM to the YAG position. Alias for move("YAG").

        Returns
        -------
        status : MoveStatus
            Status object of the move        
        """
        return self.move("YAG", wait=wait, **kwargs)

    def move_out(self, wait=True, **kwargs):
        """
        Move the PIM to the OUT position. Alias for move("OUTx").
        
        Returns
        -------
        status : MoveStatus
            Status object of the move
        """
        return self.move("OUT", wait=wait, **kwargs)

    def move_diode(self, wait=True, **kwargs):
        """
        Move the PIM to the DIODE position. Alias for move("DIODE").

        Returns
        -------
        status : MoveStatus
            Status object of the move
        """
        return self.move("DIODE", wait=wait, **kwargs)

    def move(self, position, wait=True, **kwargs):
        """
        Move the PIM to the inputted position, optionally waiting for the move
        to complete. String inputs are not case sensitive and must be one of
        the following:

        	"DIODE", "OUT", "IN", "YAG"

        Enumerated positions can also be inputted where:

        	1 : "DIODE", 2 : "OUT", 3 : "IN", 3 : "YAG"
        
        Parameters
        ----------
        position : str or number
            String or enumerated position to move to.
        
        wait : bool, optional
            Wait for the status object to complete the move before returning

        timeout : float, optional
            Maximum time to wait for the motion. If None, the default timeout
            for this positioner is used

        settle_time: float, optional
        	Delay after the set() has completed to indicate completion to the
        	caller        

        Returns
        -------
        status : MoveStatus
            Status object of the move

        Raises
        ------
        ValueError
        	If the inputted position to move to is not a valid position
        """
        # If position is a number, check it is a valid enumeration state
        if isnumber(position) and position in (1, 2, 3):
            status = self.states.state.set(position, **kwargs)

        # If string check it is a valid state for the motor
        elif isinstance(position, str) and position.upper() in ("DIODE", "OUT",
                                                                "IN", "YAG"): 
            if position.upper() == "IN":
                status = self.states.state.set("YAG", **kwargs)
            else:
                status = self.states.state.set(position.upper(), **kwargs)
        else:
            # Invalid position inputted
            raise ValueError("Position must be a PIM valid state.")

        # Wait for the status object to register the move as complete
        if wait:
            status_wait(status)

        return status

    def mv(self, position, wait=True, **kwargs):
        """
        Moves to the inputted position. Alias for the move() method.

        Returns
        -------
        status : MoveStatus
            Status object of the move
        """        
        return self.move(position, wait=wait, **kwargs)

    def set(self, position, wait=True, **kwargs):
        """
        Moves to the inputted position. Alias for the move() method.

        Returns
        -------
        status : MoveStatus
            Status object of the move
        """        
        return self.move(position, wait=wait, **kwargs)
        
    @property
    @raise_if_disconnected
    def position(self):
        """
        Return the current position of the yag.

        Returns
        -------
        position : str
        """
        # Changing readback for "YAG" to "IN" for bluesky
        pos = self.states.state.value
        if pos == "YAG":
            return "IN"
        return pos

    @property
    @raise_if_disconnected
    def state(self):
        """
        Returns the current state of pim. Alias for self.position.

        Returns
        -------
        position : str        
        """
        return self.position

    @property
    def blocking(self):
        """
        Bool for if the yag is in a blocking position.

        Returns
        -------
        blocking : bool
        """
        # Out and diode do not interfere with beam propagation
        if self.states.value in ("OUT", "DIODE"):
            return False
        return True

    @property
    def inserted(self):
        """
        Bool for if the yag is inserted. Alias for blocking.

        Returns
        -------
        inserted : bool
        """
        return self.blocking


class PIM(PIMMotor):
    """
    Full profile intensity monitor including the motor to move the yag, and the
    detector to view it.

    Components
    ----------
    detector : PIMPulnixDetector
    	Pulnix detector used in the PIMs

    Parameters
    ----------
    prefix : str
        The EPICS base of the motor

    prefix_det : str, optional
        The EPICS base PV of the detector. If None, it will be inferred from the
    	motor prefix

    read_attrs : sequence of attribute names, optional
        The signals to be read during data acquisition (i.e., in read() and
        describe() calls)

    configuration_attrs : sequence of attribute names, optional
        The signals to be returned when asked for the motor configuration (i.e.
        in read_configuration(), and describe_configuration() calls)

    name : str, optional
        The name of the offset mirror
    """
    detector = FormattedComponent(PIMPulnixDetector, "{self._prefix_det}",
                                  read_attrs=['stats2'])

    def __init__(self, prefix, prefix_det=None, **kwargs):
        # Infer the detector PV from the motor PV
        if not prefix_det:
            self._section = prefix.split(":")[0]
            self._imager = prefix.split(":")[1]
            self._prefix_det = "{0}:{1}:CVV:01".format(
                self._section, self._imager)
        else:
            self._prefix_det = prefix_det
        super().__init__(prefix, **kwargs)
        
        # Override check_camera to include checking the yag has been inserted
        self.detector.check_camera = self.check_camera

    def check_camera(self):
        """
        Checks if the camera is acquiring images.

        Raises
        ------
        NotInsertedError
        	Error raised if the camera is not in the inserted position
        NotAcquiringError
        	Error raised if the camera is not acquiring
        """
        if not self.detector.acquiring:
            raise NotAcquiringError
        if not self.inserted:
            raise NotInsertedError
    
    
class PIMFee(Device):
    """
    PIM class for the PIMs in the FEE that run using Dehong's custom ioc.

    Components
    ----------
    detector : FeeOpalDetector
    	Detector used in the PIM

    yag : ImsMotor
    	Motor that controls the position of the yag
    
    zoom : ImsMotor
    	Motor that controls the zoom

    focus : ImsMotor
    	Motor that controls the focus

    go : EpicsSignal
    	Signal to move the yag in and out

    pos : EpicsSignalRO
    	Readback for the position as a state

    Parameters
    ----------
    prefix : str
        The EPICS base of the motor and detector

    prefix_pos : str, optional
        The EPICS base PV of the state PVs

    read_attrs : sequence of attribute names, optional
        The signals to be read during data acquisition (i.e., in read() and
        describe() calls)

    configuration_attrs : sequence of attribute names, optional
        The signals to be returned when asked for the motor configuration (i.e.
        in read_configuration(), and describe_configuration() calls)

    name : str, optional
        The name of the offset mirror
    """
    # Opal
    detector = FormattedComponent(FeeOpalDetector, "{self._prefix}", 
                                name="Opal Camera")

    # Yag Motors
    yag = FormattedComponent(ImsMotor, "{self._prefix}:MOTR", 
                             ioc="{self._ioc}", name="Yag Motor")
    zoom = FormattedComponent(ImsMotor, "{self._prefix}:CLZ:01", 
                              ioc="{self._ioc}", name="Zoom Motor")
    focus = FormattedComponent(ImsMotor, "{self._prefix}:CLF:01", 
                               ioc="{self._ioc}", name="Focus Motor")
    
    # Position PV
    go = FormattedComponent(EpicsSignal, "{self._prefix_pos}:YAG:GO")
    pos = FormattedComponent(EpicsSignalRO, "{self._prefix_pos}:POSITION")

    def __init__(self, prefix, *, prefix_pos="", ioc="", in_pos=0, out_pos=43, 
                 read_attrs=None, name=None, parent=None, 
                 configuration_attrs=None, **kwargs):        
        self._prefix = prefix
        self._prefix_pos = prefix_pos
        self._ioc=ioc
        self.in_pos = in_pos
        self.out_pos = out_pos

        if read_attrs is None:
            read_attrs = ['detector', 'zoom', 'focus', 'yag', 'pos']
        if configuration_attrs is None:
            configuration_attrs = ['detector', 'zoom', 'focus', 'yag', 'pos']
            
        super().__init__(prefix, read_attrs=read_attrs, name=name, parent=parent,
                         configuration_attrs=configuration_attrs, **kwargs)    

    def check_camera(self):
        """
        Checks if the camera is acquiring images.

        Raises
        ------
        NotInsertedError
        	Error raised if the camera is not in the inserted position
        NotAcquiringError
        	Error raised if the camera is not acquiring
        """
        if not self.detector.acquiring:
            raise NotAcquiringError
        if not self.inserted:
            raise NotInsertedError

    def move_in(self, wait=True, **kwargs):
        """
        Move the PIM to the IN position. Alias for move("IN").
        
        Returns
        -------
        status : MoveStatus
            Status object of the move
        """
        return self.move("IN", wait=wait, **kwargs)

    def move_out(self, wait=True, **kwargs):
        """
        Move the PIM to the OUT position. Alias for move("OUT").

        Returns
        -------
        status : MoveStatus
            Status object of the move
        """
        return self.move("OUT", wait=wait, **kwargs)

    def move(self, position, wait=True, **kwargs):
        """
        Move the yag motor to the inputted state, optionally waiting for the
        move to complete. String inputs are not case sensitive and must be one of
        the following:

        	"IN", "OUT"

        If a number is passed then the yag motor will be moved the inputted
        position.
        
        Parameters
        ----------
        position : str or number
            String or position to move to.
        
        wait : bool, optional
            Wait for the status object to complete the move before returning

        timeout : float, optional
            Maximum time to wait for the motion. If None, the default timeout
            for this positioner is used

        settle_time: float, optional
        	Delay after the set() has completed to indicate completion to the
        	caller                

        Returns
        -------
        status : MoveStatus
            Status object of the move

        Raises
        ------
        ValueError
        	If the inputted position to move to is not a valid position        
        """
        # Handle string inputs
        if isinstance(position, str):
            if position.upper() in ("IN", "OUT"):
                status = go.set(position.upper(), **kwargs)
            else:
                raise ValueError("Position must be a PIM valid state.")

        # Handle position inputs
        elif isnumber(position):
            status = yag.move(position, wait=wait, **kwargs)

        # Everything else
        else:
            raise ValueError("Position must be a PIM valid state.")

        # Wait for the status object to register the move as complete
        if wait:
            status_wait(status)

        return status

    def mv(self, position, **kwargs):
        return self.move(position, **kwargs)
        
    @property
    @raise_if_disconnected
    def position(self):
        """
        Return the current position of the yag.

        Returns
        -------
        position : str        
        """
        return self.pos.value

    @property
    @raise_if_disconnected
    def state(self):
        """
        Returns the current state of the yag. Alias for self.position.

        Returns
        -------
        position : str                
        """
        return self.position

    @property
    @raise_if_disconnected
    def image(self):
        """
        Returns the image stream reshaped to be the correct size using the size
        component in cam.

        Returns
        -------
        image : np.ndarray
        	Image array
        """
        return np.reshape(np.array(self.cam.array_data.value),
                          (self.cam.size.size_y.value,
                           self.cam.size.size_x.value))
                         
    @property
    @raise_if_disconnected
    def blocking(self):
        """
        Bool for if the yag is in a blocking position.

        Returns
        -------
        blocking : bool
        """        
        return not bool(self.pos.value)

    @property
    def inserted(self):
        """
        Bool for if the yag is inserted. Alias for blocking.

        Returns
        -------
        inserted : bool
        """
        return self.blocking


##############
# Exceptions #
##############


class PIMExceptions(Exception):
    """
    Base exception class for the PIM.
    """
    pass


class NotAcquiringError(PIMExceptions):
    """
    Error raised if an operation requiring the camera to be acquiring is
    requested while the camera is not acquiring images.
    """
    def __init__(self, *args, **kwargs):
        self.msg = kwargs.pop("msg", "Camera currently not acquiring images.")
        super().__init__(*args, **kwargs)
    def __str__(self):
        return repr(self.msg)


class NotInsertedError(PIMExceptions):
    """
    Error raised if an operation requiring the yag be inserted is requested but
    the yag is not in the inserted position.
    """
    def __init__(self, *args, **kwargs):
        self.msg = kwargs.pop(
            "msg", "Camera currently not in inserted position.")
        super().__init__(*args, **kwargs)
    def __str__(self):
        return repr(self.msg)
