# Implementation of serial protocol for iColor3
# http://www.colorkinetics.com/support/userguides/iPlayer_3_UG.pdf


import serial
import logging


class IColor3SerialError(Exception):
    pass


class IColor3Error(Exception):
    pass


class SerialAPI:
    def __init__(self, config):
        self.logger = logging.getLogger('pycolor3.SerialAPI')
        self.conn = serial.Serial()

        # Settings for iColor3
        self.conn.baudrate = 9600
        self.conn.bytesize = 8
        self.conn.parity = 'N'
        self.conn.stopbits = 1

        # Configured via Flask app
        self.conn.timeout = config['SERIAL_TIMEOUT']
        self.conn.port = config['SERIAL_DEVICE']

    # context manager hoooks
    def __enter__(self):
        self.conn.open()
        return self

    def __exit__(self, *args):
        self.conn.close()

    def validate(self, input):

        if not isinstance(input, int):
            raise TypeError(input)

        # 0-255 are the only valid inputs for iColor3 serial params.
        if input > 255 or input < 0:
            raise ValueError('Invalid input value: ' + str(input))

        return input

    def send_command(self, prefix, input):

        if not self.conn.is_open:
            raise IColor3SerialError('Serial connection is not open.')

        command = prefix + hex(input)[2:].zfill(2).upper()
        self.conn.write(command.encode())
        self.logger.debug('sent command to iColor3: ' + command)

        response = self.conn.read(5)
        if not response:
            return False

        response = response.decode()
        self.logger.debug('iColor3 responded: ' + response)

        # If commands are successful it always responds back with the same command, switching X for Y.
        #TODO: Handle common errors.
        if response.replace('Y', 'X') != command:
            raise IColor3Error(response)

        return True

    def play_show(self, show_number):
        return self.send_command("X04", self.validate(show_number))

    def turn_off(self):
        return self.send_command("X01", "00")

    def set_brightness(self, brightness):
        return self.send_command("X02", self.validate(brightness))
