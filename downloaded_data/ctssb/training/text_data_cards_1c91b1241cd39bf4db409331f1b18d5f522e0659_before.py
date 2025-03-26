# -*- coding: utf-8 -*-

# To parse ATP files, the fortranformat module is used
# Install from pip: pip install fortranformat
from fortranformat import FortranRecordReader
from fortranformat import FortranRecordWriter
# from fortranformat import RecordError

import copy


class DataCard:
    """ Class to implement a line of generalized ATP/Fortran style input records
        format is a format string suitable for the fortranformat module.
        fields is a list of field names for indexing the data dict. Field names
            will usually be strings, but could be integers or floats in the
            case of matching fixed_fields.
        fixed_fields is an iterable of field indices that have fixed values.
            The expected value for the field should be the field name in the
            fields  list.
        Data in the line is internally represented using a dict.

        format and fields should not be changed after initialization.

        Reads only one line, but should be passed an interable of lines.
    """

    def __init__(self, format, fields, fixed_fields=(), name=None):
        self._fields = fields
        self._fixed_fields = tuple(fixed_fields)
        self._reader = FortranRecordReader(format)
        self._writer = FortranRecordWriter(format)
        self.name = name

        self.data = {}
        for f in fields:
            if f is not None:
                self.data[f] = None

    def read(self, lines):
        """ Read in datalines with validation prior to populating data. """
        if not self.match(lines):
            # This should raise an exception and will help
            # identify where in the stack the exception occured.
            tmp = copy.deepcopy(self)
            tmp._read(lines)
        self._read(lines)

    def _read(self, lines):
        line = lines[0]
        data = self._reader.read(line)
        for f in self._fixed_fields:
            if data[f] != self._fields[f]:
                raise ValueError('Fixed field with wrong value: ' + data[f] +
                                 '/' + self._fields[f])

        for f, d in zip(self._fields, data):
            if f is not None:
                self.data[f] = d

        return self

    def write(self):
        data = [self.data[f] if f is not None else None for f in self._fields]
        return self._writer.write(data)

    def match(self, lines):
        """ Checks if text lines match record type. Does not modify card data.
        """
        tmp = copy.deepcopy(self)
        try:
            tmp._read(lines)
        except ValueError:
            return False

        return True

    def num_lines(self):
        return 1


class DataCardFixedText(DataCard):
    def __init__(self, text, name=None):
        DataCard.__init__(self, format='(A%d)' % len(text),
                          fields=[text], fixed_fields=(0,), name=None)


class DataCardStack(DataCard):
    """ Class to implement generalized ATP/Fortran style input records.
        datalines is a list of DataLine objects. It represents a single data
        card that spans multiple lines. Fields must be unique among all lines.

        data is represented internally using a dict.

        TODO: List of cards with termination card. Different class??
    """

    def __init__(self, datalines, name=None):
        self._datalines = copy.deepcopy(datalines)
        self.name = name
        self._fixed_fields = ()

        self.data = {}
        for dl in self._datalines:
            for f in dl._fields:
                self.data[f] = None

    def _read(self, lines):
        """ Read in datalines with no validation. Throw ValueError if records
            don't match up.
        """
        line_idx = 0
        for dl in self._datalines:
            dl._read(lines[line_idx:])
            line_idx += dl.num_lines()
            # Sync data up to DataCardFixed.data dict.
            for f in dl._fields:
                self.data[f] = dl.data[f]
            if dl.name is not None:
                self.data[dl.name] = dl.data

        return self

    def write(self):
        rtn = []
        for dl in self._datalines:
            # Sync data down to DataLine.data dicts.
            for f in dl._fields:
                dl.data[f] = dl.data[f]
            rtn.append(dl.write())
        return '\n'.join(rtn)

    def num_lines(self):
        return sum([dl.num_lines() for dl in self._datalines])


class DataCardRepeat(DataCardStack):
    """ Class to implement ATP/Fortram style input records where a record
        may be repeated some number of times. Records are read until an
        end-marker record is found.

        For now, repeated_record and end_record have to be a single-line
        records. That restriction should change in the future, but it will
        probably require changing the interface to the other classes to an
        iterator or similar.

        Data is stored as a list of cards. Access by index or iteration only at
        this time.
    """

    def __init__(self, repeated_record, end_record, name=None):
        self._repeated_record = copy.deepcopy(repeated_record)
        self.end_record = copy.deepcopy(end_record)
        self._datalines = []
        self.data = []
        self.name = name
        self._fields = []

    def _read(self, lines):

        self.data = []
        # Loop breaks internally due to complexity of break conditions
        line_idx = 0
        while line_idx < len(lines):
            if self.end_record.match(lines[line_idx:]):
                self._datalines.append(self.end_record)
                self.end_record._read(lines[line_idx:])
                line_idx += self.end_record.num_lines()
                break
            # Read record and append to records list
            r = copy.deepcopy(self._repeated_record)
            self._datalines.append(r)
            r._read(lines[line_idx:])
            line_idx += r.num_lines()
            self.data.append(r.data)

        return self
