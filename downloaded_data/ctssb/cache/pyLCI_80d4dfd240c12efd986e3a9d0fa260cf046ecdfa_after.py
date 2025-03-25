#!/usr/bin/python

#
# based on code from Adafruit, lrvick and LiquidCrystal
# lrvick - https://github.com/lrvick/raspi-hd44780/blob/master/hd44780.py
# LiquidCrystal - https://github.com/arduino/Arduino/blob/master/libraries/LiquidCrystal/LiquidCrystal.cpp
# Adafruit - https://github.com/adafruit/Adafruit-Raspberry-Pi-Python-Code
#

from time import sleep

def delayMicroseconds(microseconds):
    seconds = microseconds / float(1000000)  # divide microseconds by 1 million for seconds
    sleep(seconds)

def delay(milliseconds):
    seconds = milliseconds / float(1000)  # divide microseconds by 1 million for seconds
    sleep(seconds)


class HD44780():

    # commands
    LCD_CLEARDISPLAY        = 0x01
    LCD_RETURNHOME          = 0x02
    LCD_ENTRYMODESET        = 0x04
    LCD_DISPLAYCONTROL      = 0x08
    LCD_CURSORSHIFT         = 0x10
    LCD_FUNCTIONSET         = 0x20
    LCD_SETCGRAMADDR        = 0x40
    LCD_SETDDRAMADDR        = 0x80

    # flags for display entry mode
    LCD_ENTRYRIGHT          = 0x00
    LCD_ENTRYLEFT           = 0x02
    LCD_ENTRYSHIFTINCREMENT = 0x01
    LCD_ENTRYSHIFTDECREMENT = 0x00

    # flags for display on/off control
    LCD_DISPLAYON           = 0x04
    LCD_DISPLAYOFF          = 0x00
    LCD_CURSORON            = 0x02
    LCD_CURSOROFF           = 0x00
    LCD_BLINKON             = 0x01
    LCD_BLINKOFF            = 0x00

    # flags for display/cursor shift
    LCD_DISPLAYMOVE         = 0x08
    LCD_CURSORMOVE          = 0x00

    # flags for display/cursor shift
    LCD_DISPLAYMOVE         = 0x08
    LCD_CURSORMOVE          = 0x00
    LCD_MOVERIGHT           = 0x04
    LCD_MOVELEFT            = 0x00

    # flags for function set
    LCD_8BITMODE            = 0x10
    LCD_4BITMODE            = 0x00
    LCD_2LINE               = 0x08
    LCD_1LINE               = 0x00
    LCD_5x10DOTS            = 0x04
    LCD_5x8DOTS             = 0x00

    row_offsets = [0x00, 0x40, 0x14, 0x54]

    display_function = LCD_FUNCTIONSET | LCD_4BITMODE | LCD_2LINE | LCD_5x8DOTS
    displaycontrol = 0x0c
    displaymode = 0x07

    def __init__(self, cols = 16, rows=2, debug = False):
        self.cols = cols
        self.rows = rows
        self.debug = debug

    def init_display(self, autoscroll=False):
        self.write_byte(0x30)  # initialization
        delay(20)
        self.write_byte(0x30)  # initialization
        delay(20)
        self.write_byte(0x30)  # initialization
        delay(20)
        self.home()
        self.write_byte(self.display_function)
        self.write_byte(0x08)
        self.display()
        if autoscroll:
            self.autoscroll()
        else:
            self.noAutoscroll()
        self.clear()

    def display_data(self, *args):
        self.clear()
        args = args[:self.rows]
        for line, arg in enumerate(args):
            self.setCursor(line, 0)
            self.println(arg[:self.cols].ljust(self.cols))

    def println(self, line):
        for char in line:
            self.write_byte(ord(char), char_mode=True)     

    def home(self):
        self.write_byte(self.LCD_RETURNHOME)  # set cursor position to zero
        delayMicroseconds(3000)  # this command takes a long time!

    def clear(self):
        self.write_byte(self.LCD_CLEARDISPLAY)  # command to clear display
        delayMicroseconds(3000)  # 3000 microsecond sleep, clearing the display takes a long time

    def setCursor(self, row, col):
        """ Set current input cursor to row and column specified """
        self.write_byte(self.LCD_SETDDRAMADDR | (col + self.row_offsets[row]))

    def noDisplay(self):
        """ Turn the display off (quickly) """
        self.displaycontrol &= ~self.LCD_DISPLAYON
        self.write_byte(self.LCD_DISPLAYCONTROL | self.displaycontrol)

    def display(self):
        """ Turn the display on (quickly) """
        self.displaycontrol |= self.LCD_DISPLAYON
        self.write_byte(self.LCD_DISPLAYCONTROL | self.displaycontrol)

    def noCursor(self):
        """ Turns the underline cursor off """
        self.displaycontrol &= ~self.LCD_CURSORON
        self.write_byte(self.LCD_DISPLAYCONTROL | self.displaycontrol)

    def cursor(self):
        """ Turns the underline cursor on """
        self.displaycontrol |= self.LCD_CURSORON
        self.write_byte(self.LCD_DISPLAYCONTROL | self.displaycontrol)

    def noBlink(self):
        """ Turn the blinking cursor off """
        self.displaycontrol &= ~self.LCD_BLINKON
        self.write_byte(self.LCD_DISPLAYCONTROL | self.displaycontrol)

    def blink(self):
        """ Turn the blinking cursor on """
        self.displaycontrol |= self.LCD_BLINKON
        self.write_byte(self.LCD_DISPLAYCONTROL | self.displaycontrol)

    def scrollDisplayLeft(self):
        """ These commands scroll the display without changing the RAM """
        self.write_byte(self.LCD_CURSORSHIFT | self.LCD_DISPLAYMOVE | self.LCD_MOVELEFT)

    def scrollDisplayRight(self):
        """ These commands scroll the display without changing the RAM """
        self.write_byte(self.LCD_CURSORSHIFT | self.LCD_DISPLAYMOVE | self.LCD_MOVERIGHT)

    def leftToRight(self):
        """ This is for text that flows Left to Right """
        self.displaymode |= self.LCD_ENTRYLEFT
        self.write_byte(self.LCD_ENTRYMODESET | self.displaymode)

    def rightToLeft(self):
        """ This is for text that flows Right to Left """
        self.displaymode &= ~self.LCD_ENTRYLEFT
        self.write_byte(self.LCD_ENTRYMODESET | self.displaymode)

    def autoscroll(self):
        """ This will 'right justify' text from the cursor """
        self.displaymode |= self.LCD_ENTRYSHIFTINCREMENT
        self.write_byte(self.LCD_ENTRYMODESET | self.displaymode)

    def noAutoscroll(self):
        """ This will 'left justify' text from the cursor """
        self.displaymode &= ~self.LCD_ENTRYSHIFTINCREMENT
        self.write_byte(self.LCD_ENTRYMODESET | self.displaymode)
