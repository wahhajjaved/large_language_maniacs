# Copyright (c) FIRST 2008-2012. All Rights Reserved.
# Open Source Software - may be modified and shared by FRC teams. The code
# must be accompanied by the FIRST BSD license file in the root directory of
# the project.

import threading

import hal
import sys
import traceback

from .motorsafety import MotorSafety
from .timer import Timer

__all__ = ["DriverStation"]

JOYSTICK_UNPLUGGED_MESSAGE_INTERVAL = 1.0

class DriverStation:
    """Provide access to the network communication data to / from the Driver
    Station."""

    #: The number of joystick ports
    kJoystickPorts = 6

    class Alliance:
        """The robot alliance that the robot is a part of"""
        Red = 0
        Blue = 1
        Invalid = 2

    @staticmethod
    def getInstance():
        """Gets the global instance of the DriverStation

        :returns: DriverStation
        """
        if not hasattr(DriverStation, "instance"):
            DriverStation.instance = DriverStation()
        return DriverStation.instance

    def __init__(self):
        """DriverStation constructor.

        The single DriverStation instance is created statically with the
        instance static member variable.
        """
        self.mutex = threading.RLock()
        self.dataSem = threading.Condition(self.mutex)

        self.packetDataAvailableMutex = hal.initializeMutexNormal()
        self.packetDataAvailableSem = hal.initializeMultiWait()
        hal.HALSetNewDataSem(self.packetDataAvailableSem)
        
        self.nextMessageTime = 0.0

        self.userInDisabled = False
        self.userInAutonomous = False
        self.userInTeleop = False
        self.userInTest = False
        self.newControlData = False

        self.thread_keepalive = True

        self.thread = threading.Thread(target=self.task, name="FRCDriverStation")
        self.thread.daemon = True
        self.thread.start()

    def __del__(self):
        hal.deleteMultiWait(self.packetDataAvailableSem)
        hal.deleteMutex(self.packetDataAvailableMutex)

    def release(self):
        """Kill the thread"""
        self.thread_keepalive = False

    def task(self):
        """Provides the service routine for the DS polling thread."""
        safetyCounter = 0
        while self.thread_keepalive:
            hal.takeMultiWait(self.packetDataAvailableSem,
                              self.packetDataAvailableMutex, 0)
            with self.dataSem:
                self.dataSem.notify_all()
            # need to get the control word to keep the motors enabled
            hal.HALGetControlWord()
            with self.mutex:
                self.newControlData = True
            safetyCounter += 1
            if safetyCounter >= 5:
                MotorSafety.checkMotors()
                safetyCounter = 0
            if self.userInDisabled:
                hal.HALNetworkCommunicationObserveUserProgramDisabled()
            if self.userInAutonomous:
                hal.HALNetworkCommunicationObserveUserProgramAutonomous()
            if self.userInTeleop:
                hal.HALNetworkCommunicationObserveUserProgramTeleop()
            if self.userInTest:
                hal.HALNetworkCommunicationObserveUserProgramTest()

    def waitForData(self, timeout = None):
        """Wait for new data or for timeout, which ever comes first.  If
        timeout is None, wait for new data only.

        :param timeout: The maximum time in milliseconds to wait.
        """
        with self.dataSem:
            self.dataSem.wait(timeout)

    def getBatteryVoltage(self):
        """Read the battery voltage.

        :returns: The battery voltage."""
        return hal.getVinVoltage()
    
    def _reportJoystickUnpluggedError(self, message):
        currentTime = Timer.getFPGATimestamp()
        if currentTime > self.nextMessageTime:
            self.reportError(message, False)
            self.nextMessageTime = currentTime + JOYSTICK_UNPLUGGED_MESSAGE_INTERVAL

    def getStickAxis(self, stick, axis):
        """Get the value of the axis on a joystick.
        This depends on the mapping of the joystick connected to the specified
        port.

        :param stick: The joystick port number
        :param axis: The analog axis value to read from the joystick.
        :returns: The value of the axis on the joystick.
        """
        if stick < 0 or stick >= self.kJoystickPorts:
            raise IndexError("Joystick index is out of range, should be 0-%s" % self.kJoystickPorts)

        if axis < 0 or axis >= hal.kMaxJoystickAxes:
            raise IndexError("Joystick axis is out of range")

        joystickAxes = hal.HALGetJoystickAxes(stick)
        if axis >= len(joystickAxes):
            self._reportJoystickUnpluggedError("WARNING: Joystick axis %d on port %d not available, check if controller is plugged in\n" % (axis, stick))
            return 0.0
        value = joystickAxes[axis]
        if value < 0:
            return value / 128.0
        else:
            return value / 127.0
        
    def getStickAxisCount(self, stick):
        """Returns the number of axis on a given joystick port
        
        :param stick: The joystick port number
        """
        if stick < 0 or stick >= self.kJoystickPorts:
            raise IndexError("Joystick index is out of range, should be 0-%s" % self.kJoystickPorts)
        
        return len(hal.HALGetJoystickAxes(stick))

    def getStickPOV(self, stick, pov):
        """Get the state of a POV on the joystick.

        :param stick: The joystick port number
        :param pov: which POV
        :returns: The angle of the POV in degrees, or -1 if the POV is not
                  pressed.
        """
        if stick < 0 or stick >= self.kJoystickPorts:
            raise IndexError("Joystick index is out of range, should be 0-%s" % self.kJoystickPorts)

        if pov < 0 or pov >= hal.kMaxJoystickPOVs:
            raise IndexError("Joystick POV is out of range")

        joystickPOVs = hal.HALGetJoystickPOVs(stick)

        if pov >= len(joystickPOVs):
            self._reportJoystickUnpluggedError("WARNING: Joystick POV %d on port %d not available, check if controller is plugged in\n" % (pov, stick))
            return 0.0
        return joystickPOVs[pov]
    
    def getStickPOVCount(self, stick):
        """Returns the number of POVs on a given joystick port
        
        :param stick: The joystick port number
        """
        if stick < 0 or stick >= self.kJoystickPorts:
            raise IndexError("Joystick index is out of range, should be 0-%s" % self.kJoystickPorts)
        
        return len(hal.HALGetJoystickPOVs(stick))

    def getStickButton(self, stick, button):
        """The state of a button on the joystick.

        :param stick: The joystick port number
        :param button: The button number to be read.
        :returns: The state of the button.
        """
        if stick < 0 or stick >= self.kJoystickPorts:
            raise IndexError("Joystick index is out of range, should be 0-%s" % self.kJoystickPorts)

        buttons = hal.HALGetJoystickButtons(stick)
        if button > buttons.count:
            self._reportJoystickUnpluggedError("WARNING: Joystick Button %d on port %d not available, check if controller is plugged in\n" % (button, stick))
            return False
        return ((0x1 << (button - 1)) & buttons.buttons) != 0
    
    def getStickButtonCount(self, stick):
        """Gets the number of buttons on a joystick
        
        :param stick: The joystick port number
        """
        if stick < 0 or stick >= self.kJoystickPorts:
            raise IndexError("Joystick index is out of range, should be 0-%s" % self.kJoystickPorts)
        
        return hal.HALGetJoystickButtons(stick).count

    def isEnabled(self):
        """Gets a value indicating whether the Driver Station requires the
        robot to be enabled.

        :returns: True if the robot is enabled, False otherwise.
        """
        controlWord = hal.HALGetControlWord()
        return controlWord.enabled != 0 and controlWord.dsAttached != 0

    def isDisabled(self):
        """Gets a value indicating whether the Driver Station requires the
        robot to be disabled.

        :returns: True if the robot should be disabled, False otherwise.
        """
        return not self.isEnabled()

    def isAutonomous(self):
        """Gets a value indicating whether the Driver Station requires the
        robot to be running in autonomous mode.

        :returns: True if autonomous mode should be enabled, False otherwise.
        """
        controlWord = hal.HALGetControlWord()
        return controlWord.autonomous != 0

    def isTest(self):
        """Gets a value indicating whether the Driver Station requires the
        robot to be running in test mode.

        :returns: True if test mode should be enabled, False otherwise.
        """
        controlWord = hal.HALGetControlWord()
        return controlWord.test != 0

    def isOperatorControl(self):
        """Gets a value indicating whether the Driver Station requires the
        robot to be running in operator-controlled mode.

        :returns: True if operator-controlled mode should be enabled,
            False otherwise.
        """
        controlWord = hal.HALGetControlWord()
        return not (controlWord.autonomous != 0 or controlWord.test != 0)

    def isSysActive(self):
        return hal.HALGetSystemActive()

    def isBrownedOut(self):
        return hal.HALGetBrownedOut()

    def isNewControlData(self):
        """Has a new control packet from the driver station arrived since the
        last time this function was called?

        :returns: True if the control data has been updated since the last
            call.
        """
        with self.mutex:
            result = self.newControlData
            self.newControlData = False
            return result

    def getAlliance(self):
        """Get the current alliance from the FMS.

        :returns: The current alliance
        :rtype: :class:`.Alliance`
        """
        allianceStationID = hal.HALGetAllianceStation()
        if allianceStationID in (hal.kHALAllianceStationID_red1,
                                 hal.kHALAllianceStationID_red2,
                                 hal.kHALAllianceStationID_red3):
            return self.Alliance.Red
        elif allianceStationID in (hal.kHALAllianceStationID_blue1,
                                   hal.kHALAllianceStationID_blue2,
                                   hal.kHALAllianceStationID_blue3):
            return self.Alliance.Blue
        else:
            return self.Alliance.Invalid

    def getLocation(self):
        """Gets the location of the team's driver station controls.

        :returns: The location of the team's driver station controls:
            1, 2, or 3
        """
        allianceStationID = hal.HALGetAllianceStation()
        if allianceStationID in (hal.kHALAllianceStationID_red1,
                                 hal.kHALAllianceStationID_blue1):
            return 1
        elif allianceStationID in (hal.kHALAllianceStationID_red2,
                                   hal.kHALAllianceStationID_blue2):
            return 2
        elif allianceStationID in (hal.kHALAllianceStationID_red3,
                                   hal.kHALAllianceStationID_blue3):
            return 3
        else:
            return 0

    def isFMSAttached(self):
        """Is the driver station attached to a Field Management System?

        :returns: True if the robot is competing on a field being controlled
            by a Field Management System
        """
        controlWord = hal.HALGetControlWord()
        return controlWord.fmsAttached != 0

    def isDSAttached(self):
        """Is the driver station attached to the robot?

        :returns: True if the robot is being controlled by a driver station.
        """
        controlWord = hal.HALGetControlWord()
        return controlWord.dsAttached != 0

    def getMatchTime(self):
        """Return the approximate match time.
        The FMS does not currently send the official match time to the robots.
        This returns the time since the enable signal sent from the Driver
        Station.
        
        * At the beginning of autonomous, the time is reset to 0.0 seconds.
        * At the beginning of teleop, the time is reset to +15.0 seconds.
        * If the robot is disabled, this returns 0.0 seconds.

        .. warning::

            This is not an official time (so it cannot be used to argue with
            referees).

        :returns: Match time in seconds since the beginning of autonomous
        """
        return hal.HALGetMatchTime()

    @staticmethod
    def reportError(error, printTrace):
        """Report error to Driver Station, and also prints error to `sys.stderr`. 
        Optionally appends stack trace to error message.
        
        :param printTrace: If True, append stack trace to error string
        """
        errorString = error
        if printTrace:
            exc = sys.exc_info()[0]
            stack = traceback.extract_stack()[:-1]  # last one is this func
            if exc is not None: # i.e. if an exception is present
                # remove call of full_stack, the printed exception
                # will contain the caught exception caller instead
                del stack[-1]
            trc = 'Traceback (most recent call last):\n'
            stackstr = trc + ''.join(traceback.format_list(stack))
            if exc is not None:
                stackstr += '  ' + traceback.format_exc().lstrip(trc)
            errorString += ':\n' + stackstr
        #print(errorString, file=sys.stderr)
        controlWord = hal.HALGetControlWord()
        if controlWord.dsAttached != 0:
            hal.HALSetErrorData(errorString, 0)

    def InDisabled(self, entering):
        """Only to be used to tell the Driver Station what code you claim to
        be executing for diagnostic purposes only.

        :param entering: If True, starting disabled code; if False, leaving
            disabled code
        """
        self.userInDisabled = entering

    def InAutonomous(self, entering):
        """Only to be used to tell the Driver Station what code you claim to
        be executing for diagnostic purposes only.

        :param entering: If True, starting autonomous code; if False, leaving
            autonomous code
        """
        self.userInAutonomous = entering

    def InOperatorControl(self, entering):
        """Only to be used to tell the Driver Station what code you claim to
        be executing for diagnostic purposes only.

        :param entering: If True, starting teleop code; if False, leaving
            teleop code
        """
        self.userInTeleop = entering

    def InTest(self, entering):
        """Only to be used to tell the Driver Station what code you claim to
        be executing for diagnostic purposes only.

        :param entering: If True, starting test code; if False, leaving test
            code
        """
        self.userInTest = entering
