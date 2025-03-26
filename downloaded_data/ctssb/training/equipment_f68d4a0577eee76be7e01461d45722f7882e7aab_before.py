"""
This module contains classes to interface with SRS lock-in amplifiers.
"""
import serial
import warnings
import numpy as np

class LockinError(Exception):
    pass


class SR830(object):

    # The SR830 will accept either newline (\n) or carriage return (\r) as the termination for input.
    # It returns strings ending in \r, so we can use the same for both.
    termination = '\r'
    name = "lockin"

    # TODO: figure out the acceptable formats for floats
    float_format = ':.6f'

    def __init__(self, serial_device, baud_rate=19200, timeout=1):
        self.serial = serial.Serial(serial_device, baudrate=baud_rate, timeout=timeout, rtscts=True)

    def send(self, message):
        self.serial.write(message + self.termination)

    def receive(self):
        #return self.serial.readline().strip()
        return self.read_until_terminator()

    def read_until_terminator(self):
        characters = []
        while True:
            character = self.serial.read()
            if not character:  # self.serial has timed out.
                warnings.warn("Serial port timed out while reading.")
                break
            elif character == self.termination:
                break
            else:
                characters.append(character)
        return ''.join(characters).rstrip()  # Some commands seem to return both a space and carriage return.

    def send_and_receive(self, message):
        self.send(message)
        return self.receive()

    def state(self, measurement_only=False):
        rms_voltage, signal_phase = self.snap(3, 4)  # ensure that these are taken simultaneously.
        if measurement_only:
            return dict(rms_voltage=rms_voltage, voltage_phase=signal_phase)

        return {'rms_voltage': rms_voltage,
                'signal_phase': signal_phase,
                'reference_phase': self.reference_phase,
                'reference_source': self.reference_source,
                'reference_frequency': self.reference_frequency,
                'reference_trigger': self.reference_trigger,
                'detection_harmonic': self.detection_harmonic,
                'sine_output_voltage': self.sine_output_voltage,
                'input_configuration': self.input_configuration,
                'input_shield_grounding': self.input_shield_grounding,
                'input_coupling': self.input_coupling,
                'input_notch_filter': self.input_notch_filter,
                'sensitivity': self.sensitivity,
                'reserve_mode': self.reserve_mode,
                'time_constant': self.time_constant,
                'output_filter_slope': self.output_filter_slope,
                'sync_filter': self.sync_filter,
                'sample_rate': self.sample_rate,
                'identification': self.identification,
                'local': self.local,
                }

    def _wait_until_idle(self):
        while True:
            try:
                if self.no_command_in_progress:
                    break
            except ValueError:
                continue

    # The following properties and methods implement commands listed in the manaul. They appear in the same order as in
    # the manual.

    # Reference and phase commands

    @property
    def reference_phase(self):
        """
        This is the reference phase in degrees, represented by a float.
         
        This property implements the PHAS (?) command.
        """
        return float(self.send_and_receive('PHAS?'))

    @reference_phase.setter
    def reference_phase(self, phase):
        self.send(('PHAS {' + self.float_format + '}').format(phase))

    @property
    def reference_source(self):
        """
        This is the reference source, represented by an int. 
        
        This property implements the FMOD (?) command.
        """
        return int(self.send_and_receive('FMOD?'))

    @reference_source.setter
    def reference_source(self, source):
        self.send('FMOD {:d}'.format(source))

    @property
    def reference_frequency(self):
        """
        This is the reference frequency in Hertz, represented by a float.
        
        This property implements the FREQ (?) command.
        """
        return float(self.send_and_receive('FREQ?'))

    @reference_frequency.setter
    def reference_frequency(self, frequency):
        self.send(('FREQ {' + self.float_format + '}').format(frequency))

    @property
    def reference_trigger(self):
        """
        This is the reference trigger mode, represented by an int. See the manual.
        
        This property implements the RSLP (?) command.
        """
        return int(self.send_and_receive('RSLP?'))

    @reference_trigger.setter
    def reference_trigger(self, integer):
        self.send('RSLP {:d}'.format(integer))

    @property
    def detection_harmonic(self):
        """
        This is the detection harmonic, represented by an int. See the manual.
        
        This property implements the HARM (?) command.
        """
        return int(self.send_and_receive('HARM?'))

    @detection_harmonic.setter
    def detection_harmonic(self, integer):
        self.send('HARM {:d}'.format(integer))

    @property
    def sine_output_voltage(self):
        """
        The sine output voltage in volts, represented by a float.
        
        This property implements the SLVL (?) command.
        """
        return float(self.send_and_receive('SLVL?'))

    @sine_output_voltage.setter
    def sine_output_voltage(self, voltage):
        self.send(('SLVL {' + self.float_format + '}').format(voltage))

    @property
    def input_configuration(self):
        """
        This is the input configuration mode, represented by an int. See the manual.

        This property implements the ISRC (?) command.
        """
        return int(self.send_and_receive('ISRC?'))

    @input_configuration.setter
    def input_configuration(self, integer):
        self.send('ISRC {:d}'.format(integer))

    @property
    def input_shield_grounding(self):
        """
        This is the input shield grounding mode, represented by an int. See the manual.

        This property implements the IGND (?) command.
        """
        return int(self.send_and_receive('IGND?'))

    @input_shield_grounding.setter
    def input_shield_grounding(self, integer):
        self.send('IGND {:d}'.format(integer))

    @property
    def input_coupling(self):
        """
        This is the input coupling mode: AC is 0 and DC is 1.

        This property implements the ICPL (?) command.
        """
        return int(self.send_and_receive('ICPL?'))

    @input_coupling.setter
    def input_coupling(self, integer):
        self.send('ICPL {:d}'.format(integer))

    @property
    def input_notch_filter(self):
        """
        This is the input notch filter status, represented by an int. See the manual.

        This property implements the ILIN (?) command.
        """
        return int(self.send_and_receive('ILIN?'))

    @input_notch_filter.setter
    def input_notch_filter(self, integer):
        self.send('ILIN {:d}'.format(integer))

    # Gain and time constant commands

    @property
    def sensitivity(self):
        """
        This is the sensitivity, represented by an int. See the manual.
        
        This property implements the SENS (?) command.
        """
        return int(self.send_and_receive('SENS?'))

    @sensitivity.setter
    def sensitivity(self, integer):
        self.send('SENS {:d}'.format(integer))

    #sensitivity table. sensitivities[integer] -> volts
    sensitivities = ((np.array([1,2,5])[None,:])*((10.**np.arange(-9,1))[:,None])).flatten()[1:-2]

    @property
    def reserve_mode(self):
        """
        This is the reserve mode, represented by an int. See the manual.

        This property implements the RMOD (?) command.
        """
        return int(self.send_and_receive('RMOD?'))

    @reserve_mode.setter
    def reserve_mode(self, integer):
        self.send('RMOD {:d}'.format(integer))

    @property
    def time_constant(self):
        """
        This is the output time constant, represented by an int. See the manual.

        This property implements the OFLT (?) command.
        """
        return int(self.send_and_receive('OFLT?'))

    @time_constant.setter
    def time_constant(self, integer):
        self.send('OFLT {:d}'.format(integer))

    time_constant_integer_to_seconds = {0: 10e-6,
                                        1: 30e-6,
                                        2: 100e-6,
                                        3: 300e-6,
                                        4: 1e-3,
                                        5: 3e-3,
                                        6: 10e-3,
                                        7: 30e-3,
                                        8: 100e-3,
                                        9: 300e-3,
                                        10: 1.,
                                        11: 3.,
                                        12: 10.,
                                        13: 30.,
                                        14: 100.,
                                        15: 300.,
                                        16: 1e3,
                                        17: 3e3,
                                        18: 10e3,
                                        19: 30e3}

    @property
    def output_filter_slope(self):
        """
        This is the output low-pass filter slope, represented by an int. See the manual.

        This property implements the OFSL (?) command.
        """
        return int(self.send_and_receive('OFSL?'))

    @output_filter_slope.setter
    def output_filter_slope(self, integer):
        self.send('OFSL {:d}'.format(integer))

    @property
    def sync_filter(self):
        """
        This is the output synchronous filter, represented by a bool. True means that the sync filter is on if the
        reference frequency is below 200 Hz.
        
        This property implements the SYNC (?) command.
        """
        return bool(int(self.send_and_receive('SYNC?')))

    @sync_filter.setter
    def sync_filter(self, boolean):
        self.send('SYNC {:d}'.format(boolean))

    # Display and output commands

    # DDEF

    # FPOP

    # OEXP

    # AOFF

    # Aux input and output commands

    # OAUX

    # AUXV

    # Setup commands

    # OUTX

    # OVRM

    # KLCK

    # ALRM

    # SSET

    # RSET

    # Auto functions

    def auto_gain(self, wait_until_done=True):
        """
        Perform the auto gain function.

        This method implements the AGAN command.

        :param wait_until_done: If True, this function will return only when the process has completed.
        """
        self.send('AGAN')
        if wait_until_done:
            self._wait_until_idle()

    def auto_reserve(self, wait_until_done=True):
        """
        Perform the auto reserve function.

        This method implements the ARSV command.

        :param wait_until_done: If True, this function will return only when the process has completed.
        """
        self.send('ARSV')
        if wait_until_done:
            self._wait_until_idle()

    def auto_phase(self, wait_until_done=True):
        """
        Perform the auto phase function.

        This method implements the APHS command.

        :param wait_until_done: If True, this function will return only when the process has completed.
        """
        self.send('APHS')
        if wait_until_done:
            self._wait_until_idle()

    def auto_offset_X(self, wait_until_done=True):
        self.send('AOFF 1')
        if wait_until_done:
            self._wait_until_idle()

    def auto_offset_Y(self, wait_until_done=True):
        self.send('AOFF 2')
        if wait_until_done:
            self._wait_until_idle()

    def auto_offset_R(self, wait_until_done=True):
        self.send('AOFF 3')
        if wait_until_done:
            self._wait_until_idle()

    # Data storage commands

    @property
    def sample_rate(self):
        """
        This is the sample rate, represented by an int. See the manual.

        This property implements the SRAT command.
        """
        return int(self.send_and_receive('SRAT?'))

    @sample_rate.setter
    def sample_rate(self, integer):
        self.send('SRAT {:d}'.format(integer))

    # SEND

    # TRIG

    # TSTR

    # STRT

    # PAUS

    # REST

    # Data transfer commands

    @property
    def X(self):
        return float(self.send_and_receive('OUTP? 1'))

    @property
    def Y(self):
        return float(self.send_and_receive('OUTP? 2'))

    @property
    def R(self):
        return float(self.send_and_receive('OUTP? 3'))

    @property
    def theta(self):
        return float(self.send_and_receive('OUTP? 4'))

    # OUTR

    def snap(self, *parameters):
        message = 'SNAP? ' + ','.join([str(int(p)) for p in parameters])
        response = self.send_and_receive(message)
        return [float(s) for s in response.split(',')]

    # OAUX

    @property
    def aux1(self):
        return float(self.send_and_receive('OAUX? 1'))

    @property
    def aux2(self):
        return float(self.send_and_receive('OAUX? 2'))

    @property
    def aux3(self):
        return float(self.send_and_receive('OAUX? 3'))

    @property
    def aux4(self):
        return float(self.send_and_receive('OAUX? 4'))

    # SPTS

    @property
    def n_stored_points(self):
        return int(self.send_and_receive('SPTS?'))

    # TRCA

    # TRCB

    # TRCL

    # FAST

    # STRD

    # Interface commands

    def reset(self):
        """
        Reset the lock-in to its default configuration.

        This method implements the *RST command.
        """
        self.send('*RST')

    @property
    def identification(self):
        """
        This property implements the *IDN command.

        :return: a four-element tuple containing identification information.
        """
        return tuple(self.send_and_receive('*IDN?').split(','))

    @property
    def local(self):
        """
        This property implements the LOCL command.
        """
        return int(self.send_and_receive('LOCL?'))

    @local.setter
    def local(self, integer):
        self.send('LOCL {:d}'.format(integer))

    # OVRM

    def trigger(self):
        """
        This method implements the TRIG command.
        """
        self.send('TRIG')

    # Status reporting commands

    def clear_status(self):
        """
        This method implements the *CLS command.
        """
        self.send('*CLS')

    # *ESE

    @property
    def input_queue_overflow(self):
        return bool(int(self.send_and_receive('*ESR? 0')))

    @property
    def output_queue_overflow(self):
        return bool(int(self.send_and_receive('*ESR? 2')))

    @property
    def execution_or_parameter_error(self):
        return bool(int(self.send_and_receive('*ESR? 4')))

    @property
    def illegal_command(self):
        return bool(int(self.send_and_receive('*ESR? 5')))

    @property
    def key_pressed(self):
        return bool(int(self.send_and_receive('*ESR? 6')))

    @property
    def power_on(self):
        return bool(int(self.send_and_receive('*ESR? 7')))

    # *SRE

    @property
    def no_scan_in_progress(self):
        return bool(int(self.send_and_receive('*STB? 0')))

    @property
    def no_command_in_progress(self):
        return bool(int(self.send_and_receive('*STB? 1')))

    @property
    def any_error_status(self):
        return bool(int(self.send_and_receive('*STB? 2')))

    @property
    def any_lockin_status(self):
        return bool(int(self.send_and_receive('*STB? 3')))

    @property
    def interface_output_buffer_nonempty(self):
        return bool(int(self.send_and_receive('*STB? 4')))

    @property
    def any_standard_status(self):
        return bool(int(self.send_and_receive('*STB? 5')))

    @property
    def service_request(self):
        return bool(int(self.send_and_receive('*STB? 6')))

    # *PSC

    # ERRE

    @property
    def battery_error(self):
        return bool(int(self.send_and_receive('ERRS? 1')))

    @property
    def ram_error(self):
        return bool(int(self.send_and_receive('ERRS? 2')))

    @property
    def rom_error(self):
        return bool(int(self.send_and_receive('ERRS? 4')))

    @property
    def gpib_error(self):
        return bool(int(self.send_and_receive('ERRS? 5')))

    @property
    def dsp_error(self):
        return bool(int(self.send_and_receive('ERRS? 6')))

    @property
    def math_error(self):
        return bool(int(self.send_and_receive('ERRS? 7')))

    # LIAE

    @property
    def input_overload(self):
        return bool(int(self.send_and_receive('LIAS? 0')))

    @property
    def filter_overload(self):
        return bool(int(self.send_and_receive('LIAS? 1')))

    @property
    def output_overload(self):
        return bool(int(self.send_and_receive('LIAS? 2')))

    @property
    def reference_unlock(self):
        return bool(int(self.send_and_receive('LIAS? 3')))

    @property
    def reference_unlock(self):
        return bool(int(self.send_and_receive('LIAS? 3')))

    @property
    def frequency_range_switch(self):
        return bool(int(self.send_and_receive('LIAS? 4')))

    @property
    def time_constant_changed(self):
        return bool(int(self.send_and_receive('LIAS? 5')))

    @property
    def triggered(self):
        return bool(int(self.send_and_receive('LIAS? 6')))


Lockin = SR830
