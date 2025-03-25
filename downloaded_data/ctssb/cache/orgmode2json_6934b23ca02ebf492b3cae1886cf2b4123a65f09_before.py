#!/usr/bin/env python3

"""
A pure python 3 class to parse `orgmode <http://orgmode.org/>`_ files and
spit out `JSON <http://wwww.json.org>`_. To this point it is mostly intended
to parse (tagged) notes.

.. moduleauthor:: tpltnt
"""
class Orgmode2json(object):
    """
    A pure python 3 class to parse `orgmode <http://orgmode.org/>`_ files and
    spit out `JSON <http://wwww.json.org>`_.

    .. moduleauthor:: tpltnt
    """

    __orgmode_inputfile = None
    __json_outputfile = None

    def __init__(self):
        pass

    def open_orgmodefile(self, filename):
        """
        Open a orgmode file for reading. The file is identified by the given
        name.

        :param filename: name (path) of the file to open
        :type filename: str
        :returns: file object associated with the file
        :raises: TypeError
        """

        if not isinstance(str, filename):
            raise TypeError("given filename is not a string")

        pass
