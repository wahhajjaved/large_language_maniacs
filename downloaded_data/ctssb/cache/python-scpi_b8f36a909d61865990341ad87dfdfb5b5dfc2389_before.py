"""Generic SCPI commands, allow sending and reading of raw data, helpers to parse information"""
import time
import re

from exceptions import RuntimeError, ValueError
from .errors import TimeoutError, CommandError
import decimal

from threading import Lock

class scpi(object):
    """Sends commands to the transport and parses return values"""
    def __init__(self, transport, *args, **kwargs):
        super(scpi, self).__init__(*args, **kwargs)
        self.transport = transport
        self.transport.set_message_callback(self.message_received)
        self.message_stack = []
        self.error_format_regex = re.compile(r"([+-]?\d+),\"(.*?)\"")
        self.command_timeout = 1.5 # Seconds
        self.ask_default_wait = 0 # Seconds
        self.transport_lock = Lock()
    
    def quit(self):
        """Shuts down any background threads that might be active"""
        self.transport.quit()

    def message_received(self, message):
        #print " *** Got message '%s' ***" % message
        self.message_stack.append(message)
        pass

    def parse_error(self, message):
        """Parses given message for error code and string, raises error if message format is invalid"""
        match = self.error_format_regex.search(message)
        if not match:
            # PONDER: Make our own exceptions ??
            raise ValueError("message '%s' does not have correct error format" % message)
        code = int(match.group(1))
        errstr = match.group(2)
        return (code, errstr)

    def send_command_unchecked(self, command, expect_response=True, force_wait=None):
        """Sends the command, waits for all data to complete (and if response is expected for new entry to message stack).
        The force_wait parameter is in seconds, if we know the device is going to take a while processing the request we can use this to avoid nasty race conditions"""
        self.transport_lock.acquire()
        try:
            if force_wait == None:
                force_wait = self.ask_default_wait
            stack_size_start = len(self.message_stack)
            self.transport.send_command(command)
            time.sleep(force_wait)
            timeout_start = time.time()
            while(   self.transport.incoming_data()
                  or (    expect_response
                      and len(self.message_stack) < stack_size_start+1)
                  ):
                time.sleep(0)
                if ((time.time() - timeout_start) > self.command_timeout):
                    raise TimeoutError(command, self.command_timeout)
                    # PONDER: We might want to auto-call abort_command() ? or maybe it's better handled by a decorator or something ??
        finally:
            self.transport_lock.release()

    def send_command(self, command, expect_response=True, force_wait=None):
        """Sends the command and makes sure it did not trigger errors, in case of timeout checks if there was another underlying error and raises that instead
        The force_wait parameter is in seconds, if we know the device is going to take a while processing the request we can use this to avoid nasty race conditions"""
        re_raise = None
        try:
            # PONDER: auto-add ";*WAI" ??
            self.send_command_unchecked(command, expect_response, force_wait)
        except (TimeoutError), e:
            re_raise = e
        finally:
            self.check_error(command)
            if re_raise:
                raise re_raise

    def check_error(self, command_was):
        """Checks the last error code and raises CommandError if the code is not 0 ("No error")"""
        self.send_command_unchecked("SYST:ERR?", True)
        code, errstr = self.parse_error(self.message_stack.pop())
        if code != 0:
            raise CommandError(command_was, code, errstr)
        return code

    def _parse_int(self, val):
        return None if val=="NAN" else int(val)

    def pop_str(self):
        """Pops the last value from message stack and parses it as a string"""
        data = self.message_stack.pop()
        return str(data)

    def pop_decimal(self):
        """Pops the last value from message stack and parses it as a Decimal"""
        data = self.message_stack.pop()
        return decimal.Decimal(data)

    def pop_int(self):
        """Pops the last value from message stack and parses it as an int"""
        data = self.message_stack.pop()
        return self._parse_int(data)

    def pop_float(self):
        """Pops the last value from message stack and parses it as a float"""
        data = self.message_stack.pop()
        return float(data)

    def pop_bool(self):
        """Pops the last value from message stack and parses it as a boolean"""
        data = self.message_stack.pop()
        return bool(int(data))

    def pop_str_list(self):
        """Pops the last value from message stack and parses it as a list of string values"""
        data = self.message_stack.pop()
        return str(data).split(',')

    def pop_decimal_list(self):
        """Pops the last value from message stack and parses it as a list of Decimal values"""
        data = self.message_stack.pop()
        return [decimal.Decimal(val) for val in data.split(',')]

    def pop_int_list(self):
        """Pops the last value from message stack and parses it as a list of int values"""
        data = self.message_stack.pop()
        return [self._parse_int(val) for val in data.split(',')]

    def pop_float_list(self):
        """Pops the last value from message stack and parses it as a list of float values"""
        data = self.message_stack.pop()
        return [float(val) for val in data.split(',')]

    def pop_bool_list(self):
        """Pops the last value from message stack and parses it as a list of boolean values"""
        data = self.message_stack.pop()
        return [bool(int(val)) for val in data.split(',')]

    def _ask_no_pop(self, command, force_wait=None):
        """Sends the command (checking for errors), but does NOT pop the value
        The force_wait parameter is in seconds (or none to use instance default), if we know the device is going to take a while processing
        the request we can use this to avoid nasty race conditions"""
        # TODO: Maybe check error opnly if we do not get a response ??
        re_raise = None
        try:
            self.send_command_unchecked(command, True, force_wait)
        except (TimeoutError), e:
            # This will raise the correct error in case we got a timeout waiting for the input
            self.check_error(command)
            # If there was not error, re-raise the timeout
            raise e
        # PONDER: Before returning check if there are leftover messages in the stack, that would not be a good thing...

    def ask_str(self, command, force_wait=None):
        """Sends the command (checking for errors), returning reply as a string
        The force_wait parameter is in seconds (or none to use instance default), if we know the device is going to take a while processing
        the request we can use this to avoid nasty race conditions"""
        self._ask_no_pop(command, force_wait)
        return self.pop_str()

    def ask_decimal(self, command, force_wait=None):
        """Sends the command (checking for errors), then pops and parses the last line as Decimal
        The force_wait parameter is in seconds (or none to use instance default), if we know the device is going to take a while processing
        the request we can use this to avoid nasty race conditions"""
        self._ask_no_pop(command, force_wait)
        return self.pop_decimal()

    def ask_int(self, command, force_wait=None):
        """Sends the command (checking for errors), then pops and parses the last line as int
        The force_wait parameter is in seconds (or none to use instance default), if we know the device is going to take a while processing
        the request we can use this to avoid nasty race conditions"""
        self._ask_no_pop(command, force_wait)
        return self.pop_int()

    def ask_float(self, command, force_wait=None):
        """Sends the command (checking for errors), then pops and parses the last line as float
        The force_wait parameter is in seconds (or none to use instance default), if we know the device is going to take a while processing
        the request we can use this to avoid nasty race conditions"""
        self._ask_no_pop(command, force_wait)
        return self.pop_float()

    def ask_bool(self, command, force_wait=None):
        """Sends the command (checking for errors), then pops and parses the last line as float
        The force_wait parameter is in seconds (or none to use instance default), if we know the device is going to take a while processing
        the request we can use this to avoid nasty race conditions"""
        self._ask_no_pop(command, force_wait)
        return self.pop_bool()

    def ask_str_list(self, command, force_wait=None):
        """Sends the command (checking for errors), returning reply as a list of string values
        The force_wait parameter is in seconds (or none to use instance default), if we know the device is going to take a while processing
        the request we can use this to avoid nasty race conditions"""
        self._ask_no_pop(command, force_wait)
        return self.pop_str_list()

    def ask_decimal_list(self, command, force_wait=None):
        """Sends the command (checking for errors), then pops and parses the last line as a list of Decimal values
        The force_wait parameter is in seconds (or none to use instance default), if we know the device is going to take a while processing
        the request we can use this to avoid nasty race conditions"""
        self._ask_no_pop(command, force_wait)
        return self.pop_decimal_list()

    def ask_int_list(self, command, force_wait=None):
        """Sends the command (checking for errors), then pops and parses the last line as a list of int values
        The force_wait parameter is in seconds (or none to use instance default), if we know the device is going to take a while processing
        the request we can use this to avoid nasty race conditions"""
        self._ask_no_pop(command, force_wait)
        return self.pop_int_list()

    def ask_float_list(self, command, force_wait=None):
        """Sends the command (checking for errors), then pops and parses the last line as a list of float values
        The force_wait parameter is in seconds (or none to use instance default), if we know the device is going to take a while processing
        the request we can use this to avoid nasty race conditions"""
        self._ask_no_pop(command, force_wait)
        return self.pop_float_list()

    def ask_bool_list(self, command, force_wait=None):
        """Sends the command (checking for errors), then pops and parses the last line as a list of float values
        The force_wait parameter is in seconds (or none to use instance default), if we know the device is going to take a while processing
        the request we can use this to avoid nasty race conditions"""
        self._ask_no_pop(command, force_wait)
        return self.pop_bool_list()

    def abort_command(self):
        """Shortcut to the transports abort_command call"""
        self.transport.abort_command()

class scpi_device(object):
    """Implements nicer wrapper methods for the raw commands from the generic SCPI command set"""

    def __init__(self, transport, *args, **kwargs):
        """Initializes a device for the given transport"""
        super(scpi_device, self).__init__(*args, **kwargs)
        self.scpi = scpi(transport)
        # always reset to known status on init
        self.reset()

    def quit(self):
        """Shuts down any background threads that might be active"""
        self.scpi.quit()

    def reset(self):
        """Resets the device to known state (with *RST) and clears the error log"""
        return self.scpi.send_command_unchecked("*RST;*CLS", False)

    def abort(self):
        """Tells the transport layer to issue "Device clear" to abort the command currently hanging"""
        return self.scpi.abort_command()

    def measure_voltage(self, extra_params=""):
        """Returns the measured (scalar) actual output voltage (in volts), pass extra_params string to append to the command (like ":ACDC")"""
        return self.scpi.ask_number("MEAS:SCAL:VOLT%s?" % extra_params)

    def measure_current(self, extra_params=""):
        """Returns the measured (scalar) actual output current (in amps), pass extra_params string to append to the command (like ":ACDC")"""
        return self.scpi.ask_number("MEAS:SCAL:CURR%s?" % extra_params)

    def set_measure_current_max(self, amps):
        """Sets the upper bound (in amps) of current to measure, on some devices low-current accuracy can be increased by keeping this low"""
        return self.scpi.send_command("SENS:CURR:RANG %f" % amps, False)

    def query_measure_current_max(self):
        """Returns the upper bound (in amps) of current to measure, this is not neccessarily same number as set with set_measure_current_max"""
        return self.scpi.ask_number("SENS:CURR:RANG?")

    def set_voltage(self, millivolts, extra_params=""):
        """Sets the desired output voltage (but does not auto-enable outputs) in millivolts, pass extra_params string to append to the command (like ":PROT")"""
        self.scpi.send_command("SOUR:VOLT%s %f MV" % (extra_params, millivolts), False)

    def query_voltage(self, extra_params=""):
        """Returns the set output voltage (in volts), pass extra_params string to append to the command (like ":PROT")"""
        return self.scpi.ask_number("SOUR:VOLT%s?" % extra_params)

    def set_current(self, milliamps, extra_params=""):
        """Sets the desired output current (but does not auto-enable outputs) in milliamps, pass extra_params string to append to the command (like ":TRIG")"""
        return self.scpi.send_command("SOUR:CURR%s %f MA" % (extra_params, milliamps), False)

    def query_current(self, extra_params=""):
        """Returns the set output current (in amps), pass extra_params string to append to the command (like ":TRIG")"""
        return self.scpi.ask_number("SOUR:CURR%s?" % extra_params)

    def set_output(self, state):
        """Enables/disables output"""
        return self.scpi.send_command("OUTP:STAT %d" % state, False)

    def query_output(self):
        """Returns the output state"""
        return self.scpi.ask_bool("OUTP:STAT?", True)

    def identify(self):
        """Returns the identification data, standard order is Manufacturer, Model no, Serial no (or 0), Firmware version"""
        return self.scpi.ask_str_list("*IDN?", True)

