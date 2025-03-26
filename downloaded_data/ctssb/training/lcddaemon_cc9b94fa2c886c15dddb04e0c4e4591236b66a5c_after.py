#-*- coding: utf-8 -*-
""" This script contains the abstract class for a driver. All driver defined
    in this app must subclass AbstractDriver.
"""

from drivers.exceptions import BadNumberOfString

class AbstractDriver(object):
    def line_count(self):
        """ This method must return the number of line(s) available
            on the screen.
        """
        raise NotImplementedError()

    def write_lines(self, tuple_of_string):
        """ This method take a tuple containing strings in parameters and
            make the screen display these lines (one string by line).

        Keyword Arguments:
            tuple_of_string - A tuple that contains strings to be display on
                              the screen.
        """
        if len(tuple_of_string) > self.line_count():
            raise BadNumberOfString()

    def clear(self):
        """ Clear the lcd screen.
        """
        raise NotImplementedError()
