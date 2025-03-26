# -*- coding: utf-8 -*-
from __future__ import print_function, division, absolute_import, unicode_literals

import time
from collections import namedtuple

import RPIO
from flufl.enum import Enum


### BIT PATTERNS ###

# Commands
LCD_CLEARDISPLAY = 0x01
LCD_RETURNHOME = 0x02
LCD_ENTRYMODESET = 0x04
LCD_DISPLAYCONTROL = 0x08
LCD_CURSORSHIFT = 0x10
LCD_FUNCTIONSET = 0x20
LCD_SETCGRAMADDR = 0x40
LCD_SETDDRAMADDR = 0x80

# Flags for display entry mode
LCD_ENTRYRIGHT = 0x00
LCD_ENTRYLEFT = 0x02
LCD_ENTRYSHIFTINCREMENT = 0x01
LCD_ENTRYSHIFTDECREMENT = 0x00

# Flags for display on/off control
LCD_DISPLAYON = 0x04
LCD_DISPLAYOFF = 0x00
LCD_CURSORON = 0x02
LCD_CURSOROFF = 0x00
LCD_BLINKON = 0x01
LCD_BLINKOFF = 0x00

# Flags for display/cursor shift
LCD_DISPLAYMOVE = 0x08
LCD_CURSORMOVE = 0x00

# Flags for display/cursor shift
LCD_DISPLAYMOVE = 0x08
LCD_CURSORMOVE = 0x00
LCD_MOVERIGHT = 0x04
LCD_MOVELEFT = 0x00

# Flags for function set
LCD_8BITMODE = 0x10
LCD_4BITMODE = 0x00
LCD_2LINE = 0x08
LCD_1LINE = 0x00
LCD_5x10DOTS = 0x04
LCD_5x8DOTS = 0x00

# Flags for RS pin modes
RS_INSTRUCTION = 0x00
RS_DATA = 0x01


### NAMEDTUPLES ###

PinConfig = namedtuple('PinConfig', 'rs rw e d0 d1 d2 d3 d4 d5 d6 d7 mode')
LCDConfig = namedtuple('LCDConfig', 'rows cols dotsize')


### ENUMS ###

class Direction(Enum):
    left = LCD_ENTRYRIGHT
    right = LCD_ENTRYLEFT


class ShiftMode(Enum):
    cursor = LCD_ENTRYSHIFTDECREMENT
    display = LCD_ENTRYSHIFTINCREMENT


class CursorMode(Enum):
    hide = LCD_CURSOROFF | LCD_BLINKOFF
    line = LCD_CURSORON | LCD_BLINKOFF
    blink = LCD_CURSOROFF | LCD_BLINKON


### HELPER FUNCTIONS ###

def msleep(milliseconds):
    """Sleep the specified amount of milliseconds."""
    time.sleep(milliseconds / 1000.0)


def usleep(microseconds):
    """Sleep the specified amount of microseconds."""
    time.sleep(microseconds / 1000000.0)


### MAIN ###

class CharLCD(object):

    # Init, setup, teardown

    def __init__(self, pin_rs=15, pin_rw=18, pin_e=16, pins_data=[21, 22, 23, 24],
                       numbering_mode=RPIO.BOARD):
        """
        Character LCD controller.

        The default pin numbers are based on the BOARD numbering scheme (1-26).

        You can save 1 pin by not using RW. Set ``pin_rw`` to ``None`` if you
        want this.

        Args:
            pin_rs:
                Pin for register select (RS). Default: 15.
            pin_rw:
                Pin for selecting read or write mode (R/W). Set this to
                ``None`` for read only mode. Default: 18.
            pin_e:
                Pin to start data read or write (E). Default: 16.
            pins_data:
                List of data bus pins in 8 bit mode (DB0-DB7) or in 8 bit mode
                (DB4-DB7) in ascending order. Default: [21, 22, 23, 24].
            numbering_mode:
                Which scheme to use for numbering the GPIO pins.
                Default: RPIO.BOARD (1-26).

        Returns:
            A :class:`CharLCD` instance.

        """
        # Set attributes
        self.numbering_mode = numbering_mode
        if len(pins_data) == 4:  # 4 bit mode
            self.data_bus_mode = LCD_4BITMODE
            block1 = [None] * 4
        elif len(pins_data) == 8:  # 8 bit mode
            self.data_bus_mode = LCD_8BITMODE
            block1 = pins_data[:4]
        else:
            raise ValueError('There should be exactly 4 or 8 data pins.')
        block2 = pins_data[-4:]
        self.pins = PinConfig(rs=pin_rs, rw=pin_rw, e=pin_e,
                              d0=block1[0], d1=block1[1], d2=block1[2], d3=block1[3],
                              d4=block2[0], d5=block2[1], d6=block2[2], d7=block2[3],
                              mode=numbering_mode)

        # Setup GPIO
        RPIO.setmode(self.numbering_mode)
        for pin in filter(None, self.pins)[:-1]:
            RPIO.setup(pin, RPIO.OUT)

    def setup(self, rows=4, cols=20, dotsize=8):
        """Initialize display with the specified configuration.

        Args:
            rows:
                Number of display rows (usually 1, 2 or 4). Default: 4.
            cols:
                Number of columns per row (usually 16 or 20). Default 20.
            dotsize:
                Some 1 line displays allow a font height of 10px.
                Allowed: 8 or 10. Default: 8.

        """
        # Set attributes
        self.lcd = LCDConfig(rows=rows, cols=cols, dotsize=dotsize)
        displayfunction = self.data_bus_mode | LCD_1LINE | LCD_5x8DOTS

        # LCD only uses two lines on 4 row displays
        if rows == 4:
            displayfunction |= LCD_2LINE

        # For some 1 line displays you can select a 10px font.
        assert dotsize in [8, 10], 'The ``dotsize`` argument should be either 8 or 10.'
        if dotsize == 10:
            displayfunction |= LCD_5x10DOTS

        # Initialization
        msleep(50)
        RPIO.output(self.pins.rs, 0)
        RPIO.output(self.pins.e, 0)
        if self.pins.rw is not None:
            RPIO.output(self.pins.rw, 0)

        # Choose 4 or 8 bit mode
        if self.data_bus_mode == LCD_4BITMODE:
            # Hitachi manual page 46
            self._write4bits(0x03)
            msleep(4.5)
            self._write4bits(0x03)
            msleep(4.5)
            self._write4bits(0x03)
            usleep(100)
            self._write4bits(0x02)
        elif self.data_bus_mode == LCD_8BITMODE:
            # Hitachi manual page 45
            self._write8bits(0x30)
            msleep(4.5)
            self._write8bits(0x30)
            usleep(100)
            self._write8bits(0x30)
        else:
            raise ValueError('Invalid data bus mode: {}'.format(self.data_bus_mode))

        # Write configuration to display
        self.command(LCD_FUNCTIONSET | displayfunction)
        usleep(50)

        # Configure display mode
        self._display_mode = LCD_DISPLAYON
        self._cursor_mode = int(CursorMode.hide)
        self.command(LCD_DISPLAYCONTROL | self._display_mode | self._cursor_mode)
        usleep(50)

        # Clear display
        self.clear()

        # Configure entry mode
        self._cursor_move_mode = int(Direction.right)
        self._display_shift_mode = int(ShiftMode.cursor)
        self._cursor_pos = (0, 0)
        self.command(LCD_ENTRYMODESET | self._cursor_move_mode | self._display_shift_mode)
        usleep(50)

    def close(self, clear=False):
        if clear:
            self.clear()
        RPIO.cleanup()

    # Properties

    def _get_cursor_pos(self):
        return self._cursor_pos

    def _set_cursor_pos(self, value):
        if not hasattr(value, '__getitem__') or len(value) != 2:
            raise ValueError('Cursor position should be determined by a 2-tuple.')
        row_offsets = [0x00, 0x40, 0x14, 0x54]  # TODO handle smaller displays
        self.command(LCD_SETDDRAMADDR | row_offsets[value[0]] + value[1])
        usleep(50)

    cursor_pos = property(_get_cursor_pos, _set_cursor_pos,
            doc='The cursor position as a 2-tuple (row, col).')

    def _get_cursor_move_mode(self):
        try:
            return Direction[self._cursor_move_mode]
        except ValueError:
            raise ValueError('Internal _cursor_move_mode has invalid value.')

    def _set_cursor_move_mode(self, value):
        if not value in Direction:
            raise ValueError('Cursor move mode must be of ``Direction`` type.')
        self._cursor_move_mode = int(value)
        self.command(LCD_ENTRYMODESET | self._cursor_move_mode | self._display_shift_mode)
        usleep(50)

    cursor_move_mode = property(_get_cursor_move_mode, _set_cursor_move_mode,
            doc='The cursor move direction (``Directions.left`` or ``Directions.right``).')

    def _get_write_shift_mode(self):
        try:
            return ShiftMode[self._display_shift_mode]
        except ValueError:
            raise ValueError('Internal _display_shift_mode has invalid value.')

    def _set_write_shift_mode(self, value):
        if value in ShiftMode:
            raise ValueError('Write shift mode must be of ``ShiftMode`` type.')
        self._display_shift_mode = int(value)
        self.command(LCD_ENTRYMODESET | self._cursor_move_mode | self._display_shift_mode)
        usleep(50)

    write_shift_mode = property(_get_write_shift_mode, _set_write_shift_mode,
            doc='The shift mode when writing (``ShiftMode.cursor`` or ``ShiftMode.display``).')

    def _get_display_enabled(self):
        return self._display_mode == LCD_DISPLAYON

    def _set_display_enabled(self, value):
        self._display_mode = LCD_DISPLAYON if value else LCD_DISPLAYOFF
        self.command(LCD_DISPLAYCONTROL | self._display_mode | self._cursor_mode)
        usleep(50)

    display_enabled = property(_get_display_enabled, _set_display_enabled,
            doc='Whether or not to display any characters.')

    def _get_cursor_mode(self):
        try:
            return CursorMode[self._cursor_mode]
        except ValueError:
            raise ValueError('Internal _cursor_mode has invalid value.')

    def _set_cursor_mode(self, value):
        if not value in CursorMode:
            raise ValueError('Cursor mode must be of ``CursorMode`` type.')
        self._cursor_mode = int(value)
        self.command(LCD_DISPLAYCONTROL | self._display_mode | self._cursor_mode)
        usleep(50)

    cursor_mode = property(_get_cursor_mode, _set_cursor_mode,
            doc='How the cursor should behave (``CursorMode.hide``, ' + \
                                   '``CursorMode.line`` or ``CursorMode.blink``).')

    # High level commands

    def write_string(self, value):
        """Write the specified string to the display."""
        for char in value:
            self.write(ord(char))

    def clear(self):
        """Overwrite display with blank characters and reset cursor position."""
        self.command(LCD_CLEARDISPLAY)
        msleep(2)

    def home(self):
        """Set cursor to initial position and reset any shifting."""
        self.command(LCD_RETURNHOME)
        msleep(2)

    def shift_display(self, amount):
        """Shift the display. Use negative amounts to shift left and positive
        amounts to shift right."""
        if amount == 0:
            return
        direction = LCD_MOVELEFT if amount > 0 else LCD_MOVERIGHT
        for i in xrange(abs(amount)):
            self.command(LCD_CURSORSHIFT | LCD_DISPLAYMOVE | direction)
            usleep(50)

    # Mid level commands

    def command(self, value):
        """Send a raw command to the LCD."""
        self._send(value, RS_INSTRUCTION)

    def write(self, value):
        """Write a raw byte to the LCD."""
        self._send(value, RS_DATA)

    # Low level commands

    def _send(self, value, mode):
        """Send the specified value to the display with automatic 4bit / 8bit
        selection. The rs_mode is either ``RS_DATA`` or ``RS_INSTRUCTION``."""

        # Choose instruction or data mode
        RPIO.setup(self.pins.rs, mode)

        # If the RW pin is used, set it to low in order to write.
        if self.pins.rw is not None:
            RPIO.output(self.pins.rw, 0)

        # Write data out in chunks of 4 or 8 bit
        if self.data_bus_mode == LCD_8BITMODE:
            self._write8bits(value)
        else:
            self._write4bits(value >> 4)
            self._write4bits(value)

    def _write4bits(self, value):
        """Write 4 bits of data into the data bus."""
        for i in xrange(4):
            bit = (value >> i) & 0x01
            RPIO.output(self.pins[i + 7], bit)
        self._pulse_enable()

    def _write8bits(self, value):
        """Write 8 bits of data into the data bus."""
        for i in xrange(8):
            bit = (value >> i) & 0x01
            RPIO.output(self.pins[i + 3], bit)
        self._pulse_enable()

    def _pulse_enable(self):
        """Pulse the `enable` flag to process data."""
        RPIO.output(self.pins.e, 0)
        usleep(1)
        RPIO.output(self.pins.e, 1)
        usleep(1)
        RPIO.output(self.pins.e, 0)
        usleep(100)  # commands need > 37us to settle
