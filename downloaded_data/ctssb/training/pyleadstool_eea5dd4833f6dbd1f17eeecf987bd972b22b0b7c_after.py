"""
    ~
    Copyright (c) 2016 John Schwarz


    Permission is hereby granted, free of charge, to any person
    obtaining a copy of this software and associated documentation
    files (the "Software"), to deal in the Software without
    restriction, including without limitation the rights to use, copy,
    modify, merge, publish, distribute, sublicense, and/or sell copies
    of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be
    included in all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
    EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
    MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
    NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
    BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
    ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
    CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.


As a macro, all LOC are going to be located within this module.
It may not be the best organization, but it allows easier mobility of
the produced macro.

This is intended to be run as a LibreOffice Calc macro or executed alongside
a running office program with open Excel sheets.

TODO:

*   Add ability to check for duplicates against a collection of
        previously used values.
    *   Possible implementations;
        *   XML table storing sheets/values
        *   Folder containing a file for each used input sheet,
                storing key values
*   Increase speed at which values in Excel are accessed
    *   Access whole lines of data at a time, rather than individual cells
        *   May be faster / easier to implement
    *   Disable cell display update on value change during Translation commit
*   Add message to user, asking them not to edit source sheet

Contents:

Office Interface handling
Translations
GUI

KNOWN BUGS:

*   Attempting to open two instances of the macro simultaneously will
    freeze both macros and the office program

INSTALL:
for libreoffice, requires python scripts module installed.
in ubuntu, this can be installed via
    'apt-get install libreoffice-script-provider-python'

"""

import collections
import os
import datetime  # used for saving logs by time
import pickle
import csv  # used for saving logs
import platform
import sys

from PyQt5.QtWidgets import QMessageBox, QVBoxLayout, QHBoxLayout, \
    QInputDialog, QCheckBox, QComboBox, QPushButton, QGridLayout, \
    QLineEdit, QDialog, QTableWidget, QTableWidgetItem, QListWidget, \
    QWidget, QLabel, QApplication

try:
    import xlwings as xw
except ImportError:
    xw = None

APP_FOLDER_NAME = 'leadsmacro'
SAVED_TRANSLATIONS_FOLDER_NAME = 'saved_translations'
LOG_DIR_NAME = 'logs'
SERIALIZED_OBJ_SUFFIX = '.pkl'

MAX_CELL_GAP = 10  # max distance between inhabited cells in the workbook

CACHING = True  # whether or not cells should cache accessed values

APP_WINDOW_TITLE = 'Lead Macro'
DEFAULT_WIDGET_X = 512
DEFAULT_WIDGET_Y = 512
DEFAULT_WIDGET_H = 512
DEFAULT_WIDGET_W = 524
DEFAULT_CONTENT_MARGIN_X = 15
DEFAULT_CONTENT_MARGIN_Y = 5

STANDARD_GRID_SPACING = 10  # spacing in gui grid

NONE_STRING = '< Empty >'

# colors #

DEFAULT_COLOR = -1
WHITE = 0xffffff
FIREBRICK = 0xB22222
CORAL = 0xFF7F50
ORANGE = 0xBDB76B
KHAKI = 0xF0E68C

WHITESPACE_CELL_COLOR = ORANGE
WHITESPACE_ROW_COLOR = DEFAULT_COLOR
DUPLICATE_CELL_COLOR = FIREBRICK
DUPLICATE_ROW_COLOR = DEFAULT_COLOR

# Settings Keys #

SOURCE_SHEET_KEY = 'Source Sheet'
TARGET_SHEET_KEY = 'Target Sheet'
SOURCE_START_KEY = 'Source Start'
TARGET_START_KEY = 'Target Start'
DUPLICATE_ACTION_KEY = 'Duplicate Action'
WHITESPACE_ACTION_KEY = 'Whitespace Action'
COLUMN_TRANSLATIONS_KEY = 'Column Translations'

SOURCE_COLUMN_NAME_KEY = 'source_column_name'
TARGET_COLUMN_NAME_KEY = 'target_column_name'
SOURCE_COLUMN_INDEX_KEY = 'source_column_i'
TARGET_COLUMN_INDEX_KEY = 'target_column_i'
WHITESPACE_CHK_KEY = 'check_for_whitespace'
DUPLICATE_CHK_KEY = 'check_for_duplicates'

# Row dlg settings
LOG_WRITE_KEY = 'log_write'
LOG_READ_KEY = 'log_read'
LOG_GROUP_KEY = 'log_group'

WHITESPACE_REMOVE_STR = 'Remove Whitespace'
WHITESPACE_HIGHLIGHT_STR = 'Highlight'
WHITESPACE_IGNORE_STR = 'Do nothing'

DUPLICATE_REMOVE_ROW_STR = 'Remove row'
DUPLICATE_HIGHLIGHT_STR = 'Highlight'
DUPLICATE_IGNORE_STR = 'Do nothing'

###############################################################################
# BOOK INTERFACE


class Model:
    """
    Abstract model to be extended by office interface specific
    subclasses in Office.
    """
    def __init__(self) -> None:
        raise NotImplementedError

    def __getitem__(self, item: str or int):
        """
        Gets sheet from model, either by the str name of the sheet,
        or the int index.
        :param item: str or int
        :return: Office.Sheet
        """
        raise NotImplementedError
        # implemented by office program specific subclasses

    def __iter__(self):
        """
        Gets iterator returning sheets in model
        :return: Iterator
        """
        raise NotImplementedError

    def get_sheet(
            self,
            sheet_name: str,
            row_ref_i: int=0,
            col_ref_i: int=0
    ) -> 'Sheet':
        """
        Gets sheet of passed name in Model.
        Functions the same as Model.__getitem__ except reference row
        and reference column indices may be passed to this method.
        :param sheet_name: str
        :param row_ref_i: int
        :param col_ref_i: int
        :return: Sheet
        """
        raise NotImplementedError  # todo: finish sorting these two methods out

    def sheet_exists(self, *sheet_name: str) -> str:
        """
        Checks that the passed string(s) exist in the model.
        if so, returns the first passed sheet name to do so.
        :param sheet_name: str
        :return: str
        """
        raise NotImplementedError
        # implemented by office program specific subclasses

    @property
    def sheets(self):
        """
        Returns iterator of sheets in model.
        :return: Iterator
        """
        raise NotImplementedError
        # implemented by office program specific subclasses

    @property
    def sheet_names(self):
        """
        Gets iterable of sheet names
        :return: str iterable
        """
        raise NotImplementedError


class WorkBookComponent:
    """
    Abstract class with common methods for classes that exist within
    a workbook.
    """
    sheet = None

    @property
    def parents(self):
        """
        Gets parents of WorkBookComponent (instances containing this component)
        :return: Generator[WorkBookComponent]
        """
        raise NotImplementedError

    @property
    def instantiated_parents(self):
        """
        Works as 'parents' method, but returns only parents that have
        been instantiated.
        This method was written to facilitate clearing caches when a
        sub-component has been changed
        :return: Generator[WorkBookComponent]
        """
        raise NotImplementedError

    @staticmethod
    def value_cache(getter: callable) -> callable:
        """
        decorator that caches results of the passed method
        :param getter: callable
        :return: callable
        """
        def wrapper(o, *args, **kwargs):
            # if caching is not possible, just call getter
            # to do this, find sheet and check if exclusive_editor is True
            if not o.sheet.exclusive_editor:
                return getter(*args, **kwargs)
            # get cache
            try:
                cache = o.__value_cache
            except AttributeError:
                cache = o.__value_cache = {}
            # if caching is possible, but nothing is in cache, set it
            try:
                value = cache[getter]  # try to return cached value
            except KeyError:
                value = cache[getter] = getter(o, *args, **kwargs)
            return value
        return wrapper

    @staticmethod
    def enduring_cache(getter):
        """
        Caches results of method in a cache that is not removed
        when a clear_cache method is called. This is to be used
        for methods whose results will always remain the same
        for the object they have been called upon, even if values
        of that WorkBookObject have changed.
        This method will also cache results regardless of whether
        the sheet interface obj is the exclusive editor of its values,
        since changes made by other means do not affect the returned
        values of the method being cached.
        :param getter: callable
        :return: callable
        """
        def enduring_cache_getter(o, *args, **kwargs):
            # get cache
            try:
                cache = o.__enduring_cache
            except AttributeError:
                cache = o.__enduring_cache = {}
            # if caching is possible, but nothing is in cache, set it
            try:
                value = cache[getter]  # try to return cached value
            except KeyError:
                value = cache[getter] = getter(o, *args, **kwargs)
            return value

        return enduring_cache_getter

    @staticmethod
    def clear_cache(setter):
        """
        decorator method to be used by value setter.
        amends method to clear cache of this WorkBookComponent and
        instantiated parents.
        :param setter: callable
        :return: callable
        """

        def setter_wrapper(o, *args, **kwargs) -> None:
            """
            Function wrapping passed setter method.
            first clears cached values,
            then calls original setter method with values.
            :return: None
            """
            assert isinstance(o, WorkBookComponent)
            # for each WorkBookComponent modified, clear its cache
            modified_components = \
                [o] + [parent for parent in o.instantiated_parents]
            for component in modified_components:
                try:  # try to find cache.
                    cache = component.__value_cache
                except AttributeError:
                    pass
                else:  # if cell has a cache, clear it.
                    assert isinstance(cache, dict)
                    cache.clear()
            setter(o, *args, **kwargs)  # call original value setter method

        return setter_wrapper


class Sheet(WorkBookComponent):
    """
    Abstract class for sheet handling cell values of a passed sheet.
    Inherited from by PyUno.Sheet and XW.Sheet.
    """
    i7e_sheet = None  # interface sheet obj. ie; com.sun.star...Sheet
    _reference_row_index = 0
    _reference_column_index = 0
    _content_row_start = None  # default start index of table_row iter
    _table_col_start = None  # default start index of table_col iter
    exclusive_editor = False  # true if no concurrent editing will occur

    _all_sheets = {}  # all sheets so far instantiated, by repr string

    def __init__(
            self,
            i7e_sheet,  # used by subclasses
            reference_row_index=0,  # used by subclasses
            reference_column_index=0  # used by subclasses
    ) -> None:
        self.i7e_sheet = i7e_sheet
        self.reference_column_index = reference_column_index
        self.reference_row_index = reference_row_index
        self.sheet = self  # returns self, as required by WorkBookComponent
        assert repr(self) not in Sheet._all_sheets
        Sheet._all_sheets[repr(self)] = self

    @staticmethod
    def factory(i7e_sheet, ref_row_index=0, ref_col_index=0) -> 'Sheet':
        """
        Factory method return Sheet.
        This method does not create duplicate sheets,
        instead, it returns a reference to a pre-existing sheet
        if one exists.
        :return: Sheet
        """
        sheet_class = Office.get_sheet_class()
        key = sheet_class.key(i7e_sheet)
        try:
            return Sheet._all_sheets[key]
        except KeyError:
            return sheet_class(
                i7e_sheet=i7e_sheet,
                reference_column_index=ref_col_index,
                reference_row_index=ref_row_index
            )

    def get_column(
            self,
            column_identifier: int or float or str
    ) -> 'Column':
        """
        Gets column by name if identifier is str, otherwise,
        attempts to get column by index.
        :param column_identifier: int, float, or str
        :return: Office.Column
        """
        if isinstance(column_identifier, str):
            return self.get_column_by_name(column_identifier)
        else:
            return self.get_column_by_index(column_identifier)

    def get_column_by_index(self, column_index: int) -> 'Column':
        """
        Gets column in Sheet by passed index.
        Implemented by sub-classes.
        :param column_index: int
        :return: Column
        """
        return Column.factory(
            sheet=self,
            index=column_index,
            reference_index=self.reference_column_index
        )

    def get_column_by_name(self, column_name: int or float or str) -> 'Column':
        """
        Gets column from a passed reference value which is compared
        to each cell value in the reference row.
        This function will return the first column whose name matches
        the passed value.
        :return: Office.Column
        """
        i = self.get_column_index_from_name(column_name)
        return self.get_column_by_index(i) if i is not None else None

    def get_column_index_from_name(
        self,
        column_name: int or float or str
    ) -> int or None:
        """
        Gets column index from name
        :param column_name: int, float, or str
        :return: int or None
        """
        # todo: cache this
        for x, cell in enumerate(self.reference_row):
            if cell.value == column_name:
                return x

    def get_row(self, row_identifier: int or float or str) -> 'Row':
        """
        Gets row by name if identifier is str, otherwise by index
        :param row_identifier: int, float, or str
        :return: Office.Row
        """
        if isinstance(row_identifier, str):
            return self.get_row_by_name(row_identifier)
        else:
            return self.get_row_by_index(row_identifier)

    def get_row_by_index(self, row_index: int or str) -> 'Row':
        """
        Gets row by passed index.
        Implemented by subclasses.
        :param row_index: int
        :return: Row
        """
        return Row.factory(
            sheet=self,
            index=row_index,
            reference_index=self.reference_row_index
        )

    def get_row_by_name(self, row_name: int or str or float) -> 'Row':
        """
        Gets row from a passed reference value which is compared
        to each cell value in the reference row.
        This function will return the first row whose name matches
        the passed value.
        :return: Office.Column
        """
        y = self.get_row_index_from_name(row_name)
        return self.get_row_by_index(y) if y is not None else None

    def get_row_index_from_name(
            self,
            row_name: int or float or str
    ) -> int or None:
        """
        Gets index of a row from passed name
        :param row_name: int, float, or str
        :return: int or None
        """
        for y, cell in enumerate(self.reference_column):
            if cell.value == row_name:
                return y

    def get_cell(self, cell_identifier, **kwargs) -> 'Cell':
        """
        Gets cell from Sheet.
        May be identified as;
        example_sheet.get_cell((x, y))
        example_sheet.get_cell((row_name, column_name))
        example_sheet.get_cell((row_name, y_int))
        Assumes that a passed number is a row or column index.
        If a number is to be passed as a row or sheet name,
        pass as a kwarg x_identifier_type='name' or
        y_identifier_type='name'.
        Also valid: x_identifier_type='index'
        :param cell_identifier: tuple
        :param kwargs: strings
        :return:
        """
        # if cell_identifier is list or tuple, get cell via
        # x, y coordinates
        if isinstance(cell_identifier, (list, tuple)):
            x_identifier = cell_identifier[0]
            y_identifier = cell_identifier[1]
            x_identifier_type = kwargs.get('x_identifier_type', None)
            y_identifier_type = kwargs.get('y_identifier_type', None)
            # sanity check
            assert x_identifier_type in ('index', 'name', None), \
                "x identifier type should be 'index', 'name', or None." \
                "Instead got %s" % x_identifier_type
            assert y_identifier_type in ('index', 'name', None), \
                "y identifier type should be 'index', 'name', or None." \
                'instead got %s' % y_identifier_type
            if (x_identifier_type == 'name' or
                x_identifier_type is None and isinstance(
                    x_identifier, str)):
                x = self.get_column_index_from_name(x_identifier)
            else:
                assert isinstance(x_identifier, int)  # sanity check
                x = x_identifier
            if (y_identifier_type == 'name' or
                y_identifier_type is None and isinstance(
                    y_identifier, str)):
                y = self.get_row_index_from_name(y_identifier)
            else:
                assert isinstance(y_identifier, int)  # sanity check
                y = y_identifier
            # We now have x and y indices for the cell
            # now we call the cell factory method, which returns a cell
            # of the correct type. The Cell factory method will not
            # create duplicate cells, instead it will return a
            # reference to the pre-existing cell in that sheet+position
            return Cell.factory(sheet=self, position=(x, y))

    @property
    def reference_row_index(self) -> int:
        """
        Gets index of reference row
        :return: int
        """
        return self._reference_row_index

    @reference_row_index.setter
    def reference_row_index(self, new_index: int) -> None:
        """
        Sets reference row by passing the index of the new row.
        Must be > 0
        :param new_index: int
        :return: None
        """
        if new_index < 0:
            raise IndexError('Reference row index must be > 0')
        self._reference_row_index = new_index

    @property
    def reference_row(self) -> 'Row':
        """
        Gets reference row
        :return: Office.Row
        """
        return self.get_row(self.reference_row_index)

    @property
    def reference_column_index(self) -> int:
        """
        Gets index of reference column
        :return: int
        """
        return self._reference_column_index

    @reference_column_index.setter
    def reference_column_index(self, new_index) -> None:
        """
        Sets reference column by passing the index of the new
        reference column.
        Must be > 0.
        :param new_index: int
        :return: None
        """
        if new_index < 0:
            raise IndexError('Reference row index must be > 0')
        self._reference_column_index = new_index

    @property
    def reference_column(self) -> 'Column':
        """
        Gets reference column
        :return: Office.Column
        """
        return self.get_column(self.reference_column_index)

    @property
    def columns(self) -> 'LineSeries':
        """
        Gets iterator of columns in sheet
        :return: Iterator[Column]
        """
        return LineSeries(reference_line=self.reference_row)

    @property
    def table_columns(self) -> 'LineSeries':
        """
        Gets iterator of columns in sheet's table contents
        :return: Iterator[Column]
        """
        return LineSeries(
            reference_line=self.reference_column,
            start_index=self.table_col_start_i
        )

    @property
    def table_col_start_i(self) -> int:
        """
        Gets index of first column in sheet's table.
        By default, this is the first column after the reference column.
        This value may also be explicitly set by passing an int to this
        property setter.
        :return: int
        """
        if self._table_col_start is not None:
            return self._table_col_start
        else:
            return self._reference_column_index + 1

    @table_col_start_i.setter
    def table_col_start_i(self, new_i: int) -> None:
        """
        Sets first column which is included in table_columns.
        :param new_i: int
        :return: None
        """
        if new_i is not None or not isinstance(new_i, int):
            raise TypeError(
                'New index should be an integer, or None. Got: %s'
                % repr(new_i)
            )
        self._table_col_start = new_i

    @property
    def rows(self) -> 'LineSeries':
        """
        Gets iterator of rows in Sheet.
        :return: Iterator[Row]
        """
        return LineSeries(reference_line=self.reference_column)

    @property
    def table_rows(self) -> 'LineSeries':
        """
        Gets iterator of table rows in Sheet
        :return: Iterator[Row]
        """
        return LineSeries(
            reference_line=self.reference_column,
            start_index=self.table_row_start_i
        )

    @property
    def table_row_start_i(self) -> int:
        """
        Gets index of first row in sheet's table.
        By default, this is the first row after the reference row.
        This value may also be explicitly set by passing an int to this
        property setter.
        :return: int
        """
        if self._content_row_start is not None:
            return self._content_row_start
        else:
            return self.reference_row_index + 1

    @table_row_start_i.setter
    def table_row_start_i(self, new_i: int) -> None:
        """
        Sets first row which is included in table_columns.
        :param new_i: int
        :return: None
        """
        if new_i is not None or not isinstance(new_i, int):
            raise TypeError(
                'New index should be an integer, or None. Got: %s'
                % repr(new_i)
            )
        self._content_row_start = new_i

    @property
    def screen_updating(self) -> bool or None:
        """
        Gets bool of whether screen updating occurs on sheet.
        does nothing here, may be overridden by subclasses.
        returns None if this sheet type does not support this method.
        :return: bool
        """
        return

    @screen_updating.setter
    def screen_updating(self, new_bool: bool) -> None:
        """
        Sets whether sheet refreshes its display after update of
        values, etc.
        Does nothing here, subclasses may implement this method.
        :param new_bool: bool
        :return: None
        """
        return

    @property
    def parents(self):
        return  # nothing to yield or return

    @property
    def instantiated_parents(self):
        return  # nothing to yield or return

    def __str__(self) -> str:
        raise NotImplementedError

    def __repr__(self) -> str:
        raise NotImplementedError


class LineSeries:
    """Class storing collection of Line, Column, or Row objects"""

    COLUMNS_STR = 'columns'
    ROWS_STR = 'rows'

    def __init__(
            self,
            reference_line: 'Line',
            start_index: int=0,  # iterator start index
            end_index: int=None,  # iterator end index (exclusive)
    ) -> None:
        if not isinstance(reference_line, Line):
            raise TypeError('Expected LineSeries to be passed reference line.'
                            'Got instead: %s' % repr(reference_line))
        self.reference_line = reference_line
        self.start_index = start_index
        self.end_index = end_index

    def __getitem__(self, item: int or float or str):
        """
        If item is int, returns line of that index, otherwise looks
        for a line of that name.
        :param item: int, float, or str
        :return: Line or None
        """
        if isinstance(item, int):
            return self.get_by_index(item)
        else:
            return self.get_by_name(item)

    def __iter__(self):
        """
        Returns Generator that iterates over columns in LineSeries
        :return: Generator<Line>
        """
        # find whether this is a series of rows or columns
        if self.end_index is not None:
            ref_cells = self.reference_line[self.start_index:self.end_index]
        else:
            ref_cells = self.reference_line[self.start_index:]
        for cell in ref_cells:
            if self._contents_type == LineSeries.COLUMNS_STR:
                yield cell.column
            if self._contents_type == LineSeries.ROWS_STR:
                yield cell.rows

    def __len__(self) -> int:
        """
        Returns size of LineSeries
        :return: int
        """
        count = self.start_index
        try:  # it feels like there should be a better way to do this
            assert self.end_index is None or isinstance(self.end_index, int)
            # while there is a next cell, and it is inside range
            while self.__iter__().__next__() and \
                    (self.end_index is None or count + 1 < self.end_index):
                count += 1  # increment count
        except StopIteration:
            return count

    def get_by_name(self, name: int or float or str) -> 'Line':
        """
        Gets line from passed line name.
        Returns None if no line of that name is found.
        :param name: int, float or str
        :return: Line or None
        """
        for cell in self.reference_line:
            if cell.value == name:
                if self._contents_type == LineSeries.COLUMNS_STR:
                    return cell.column
                elif self._contents_type == LineSeries.ROWS_STR:
                    return cell.row

    def get_by_index(self, index: int) -> 'Line':
        """
        Gets line from passed line index
        :param index:
        :return: Line
        """
        if self._contents_type == 'rows':
            return self.sheet.get_row_by_index(index)
        elif self._contents_type == 'columns':
            return self.sheet.get_column_by_index(index)

    @property
    def sheet(self) -> Sheet:
        """
        Gets sheet that owns the Columns or Rows of this Lines obj.
        :return: Sheet
        """
        return self.reference_line.sheet

    @property
    def names(self):
        """
        Yields names of lines in LineList
        :return: int, float, or str
        """
        for line in self:
            yield line.name

    @property
    def named_only(self):
        """
        Yields only lines in this series that have line headers
        :return:
        """
        for line in self:
            if line.name:
                yield line

    @property
    def indexes(self):
        """
        Yields indexes of lines in LineList
        :return: int
        """
        for line in self:
            yield line.index

    @property
    def _contents_type(self) -> str:
        """
        Gets the str name of line series; either 'columns' or 'rows'
        :return: str
        """
        if isinstance(self.reference_line, Row):
            return 'columns'
        elif isinstance(self.reference_line, Column):
            return 'rows'
        else:
            raise TypeError('Expected reference_line to be Row or'
                            'Column. Got: %s' % repr(self.reference_line))


class Line(WorkBookComponent):
    """
    Abstract class for a line of cells.
    Sub-classed by both Row and Column
    """
    _all = {}  # overwritten in sub-classes.

    def __init__(
        self,
        sheet: Sheet,
        index: int,
        reference_index: int,
    ) -> None:
        # check if an instance already exists in dict of all Row/Col.
        # It shouldn't.
        assert (sheet, index) not in self._all
        self._all[(sheet, index)] = self  # add self to _all dict
        if not isinstance(sheet, Sheet):
            raise TypeError(
                'Expected subclass of Sheet. Instead got %s'
                % repr(sheet))
        if not isinstance(index, int):
            raise TypeError(
                'Expected line index to be an int. '
                'Instead got %s' % repr(index))
        if index < 0:
            raise ValueError('Index must be 0 or greater. Got: %s' % index)
        if not isinstance(reference_index, int):
            raise TypeError(
                'Expected reference name index to be an int, '
                'Instead got %s' % repr(reference_index))
        if reference_index < 0:
            raise ValueError('ref index must be 0 or greater. Got: %s' % index)
        self.sheet = sheet
        self.index = index
        self.reference_index = index

    def __getitem__(self, cell_identifier):  # returns Cell or Generator
        """
        Gets cell from passed identifier.
        If identifier is string, presumes it is a cell's name.
        If identifier is number, presumes it is a
        cell's index.
        To ensure the right method of fetching a cell is used,
        use .get_by_name or .get_by_index
        :param cell_identifier: str or int
        :return: Cell
        """
        assert isinstance(cell_identifier, (int, float, str, slice)), \
            'Expected cell_identifier to be number, str, or slice got %s ' \
            % cell_identifier
        if isinstance(cell_identifier, slice):
            return self.slice(cell_identifier)
        if isinstance(cell_identifier, int):
            return self.get_cell_by_index(cell_identifier)
        else:
            return self.get_cell_by_reference(cell_identifier)

    def __iter__(self):
        raise NotImplementedError
        # implemented by office program specific subclasses

    @WorkBookComponent.value_cache
    def __len__(self) -> int:
        count = 0
        for _ in self:
            count += 1
        return count

    @classmethod
    def exists(cls, sheet: Sheet, index: int):
        """
        Returns bool of whether a line of sheet+index already exists
        :param sheet: Sheet
        :param index: int
        :return: bool
        """
        return sheet, index in cls._all

    def slice(self, s: slice):  # return cell generator
        """
        Returns generator returning items in slice
        :param s: slice
        :return: Generator[Cell]
        """
        if s.start is None:
            start = 0
        else:
            start = s.start
        if s.stop is None:
            stop = len(self)
        else:
            stop = s.stop
        if s.step is not None:
            rng = range(start, stop, s.step)
        else:
            rng = range(start, stop)
        for i in rng:
            if i in range(len(self)):
                yield self[i]

    def get_cell_by_index(self, index: int) -> 'Cell':
        """
        Gets cell in Line at passed index.
        :param index: int
        :return: Cell
        """
        raise NotImplementedError
        # implemented by Row and Column in office program
        # specific subclasses

    def get_cell_by_reference(self, reference: str or float or int) -> 'Cell':
        for i, cell in enumerate(self._reference_line):
            if cell.value == reference:
                return self.get_cell_by_index(i)

    def get_iterator(self, axis: str) -> 'CellLine':
        assert axis == 'x' or axis == 'y'
        return CellLine(self.sheet, axis, self.index)

    def clear(self, include_header: bool = False) -> None:
        """
        Clears line of cells.
        If Include header is True; clears cell data in cells
        preceding and including header row.
        :param include_header: bool
        :return: None
        """
        [cell.clear() for i, cell in enumerate(self)
         if i > self.name_cell_index or include_header]

    @property
    def _reference_line(self) -> 'Line':
        """
        Gets reference line which is parallel to this Line and
        which is used to look up names of cells in this Line.
        Implemented in sub-classes.
        :return: Line
        """
        raise NotImplementedError

    @property
    def duplicates(self):
        """
        Returns generator of duplicate cells in Column.
        :return: cells (iterator)
        """
        cell_values = set()
        for cell in self:
            if cell.value_without_whitespace in cell_values:
                yield cell
            cell_values.add(cell.value_without_whitespace)

    @property
    def name_cell_index(self) -> int:
        """
        Gets the index of the cell which contains this line's name.
        :return: int
        """
        raise NotImplementedError

    @property
    def name(self) -> int or float or str or None:
        """
        Returns name of line, which is the value stored in the
        line's header cell, located in the sheet's reference
        row or column.
        :return: int, float, str or None
        """
        return self[self.name_cell_index].value

    def to_dict(self) -> dict:
        """
        Returns line values as dictionary, with cell values as values,
        and corresponding reference row values as keys.
        :return: dict
        """
        return {line_cell.value: ref_cell.value for
                line_cell, ref_cell in zip(self, self._reference_line)}

    def __repr__(self) -> str:
        return '%s(sheet=%s, index(0-base)=%s, ref_index=%s) name: %s' % (
            self.__class__.__name__,
            repr(self.sheet),
            self.index,
            self.reference_index,
            self.name
        )

    def __str__(self) -> str:
        return '%s[index(0-base): %s] name: %s' % (
            self.__class__.__name__,
            self.index,
            self.name
        )

    @property
    def parents(self):
        yield self.sheet

    @property
    def instantiated_parents(self):
        yield self.sheet


class Column(Line):
    """
    Abstract Column class, extended by Office.XW.Column and Office.Uno.Column
    """
    _all = {}  # dict storing all unique sheet+index possibilities

    @staticmethod
    def factory(sheet: 'Sheet', index: int, reference_index: int) -> 'Column':
        """
        Factory returning a Row belonging to sheet, at passed index,
        with cell name/keys determined by reference_index.
        :param sheet: Sheet
        :param index: int
        :param reference_index: int
        :return: Column
        """
        # first try to find a pre-existing row with that sheet + index
        column_key = sheet, index  # sheet instance is expected to be unique
        try:
            column = Column._all[column_key]
        except KeyError:
            column = Office.get_column_class()(sheet, index, reference_index)
        return column

    def get_cell_by_index(self, index: int) -> 'Cell':
        """
        Gets cell in Column at passed index.
        :param index: int
        :return: Cell
        """
        if not isinstance(index, int):
            raise TypeError(
                'get_cell_by_index: passed non-int index: %s' % index
            )
        if index < 0:
            raise ValueError(
                'get_cell_by_index: passed index is < 0: %s' % index
            )
        return self.sheet.get_cell((self.index, index))

    @property
    def _reference_line(self) -> 'Line':
        return self.reference_column

    @property
    def reference_column(self) -> 'Column':
        return self.sheet.reference_column

    @property
    def name_cell_index(self) -> int:
        """
        Gets the index of the cell which contains this
        Column's name.
        :return: int
        """
        return self.sheet.reference_row_index


class Row(Line):
    """
    Abstract Row obj. Extended by Office.XW.Row and Office.Uno.Row
    """
    _all = {}  # dict storing all unique sheet+index possibilities

    @staticmethod
    def factory(sheet: 'Sheet', index: int, reference_index: int) -> 'Row':
        """
        Factory returning a Row belonging to sheet, at passed index,
        with cell name/keys determined by reference_index.
        :param sheet: Sheet
        :param index: int
        :param reference_index: int
        :return: Row
        """
        # first try to find a pre-existing row with that sheet + index
        row_key = sheet, index
        try:
            row = Row._all[row_key]
        except KeyError:
            row = Office.get_row_class()(sheet, index, reference_index)
        return row

    def get_cell_by_index(self, index: int) -> 'Cell':
        """
        Gets cell in Row at passed index.
        :param index: int
        :return: Cell
        """
        if not isinstance(index, int):
            raise TypeError(
                'get_cell_by_index: passed non-int index: %s' % index
            )
        if index < 0:
            raise ValueError(
                'get_cell_by_index: passed index is < 0: %s' % index
            )
        return self.sheet.get_cell((index, self.index))

    @property
    def _reference_line(self) -> 'Line':
        return self.reference_row

    @property
    def reference_row(self) -> 'Row':
        """
        Gets reference row.
        This is the row that contains the names of the
        intersecting columns, allowing fetching of cells in
        this row via passage of a reference string
        :return: Row
        """
        return self.sheet.reference_row

    @property
    def name_cell_index(self) -> int:
        """
        Gets the index of the cell which contains this Row's name.
        :return: int
        """
        return self.sheet.reference_column_index


class Cell(WorkBookComponent):
    """ Class handling usage of a single cell in office worksheet """
    _all_cells = {}  # dict of all created cells, prevents duplication

    def __init__(
            self,
            sheet: Sheet,
            position: tuple
    ) -> None:
        assert len(position) == 2
        assert all([isinstance(item, int) for item in position])
        self.position = tuple(position)
        self.sheet = sheet

    @staticmethod
    def factory(sheet: Sheet, position: tuple) -> 'Cell':
        """
        Gets cell belonging to sheet, with passed position.
        If a cell with the same sheet + position already exists,
        returns that cell instead.
        :param sheet: Sheet
        :param position: tuple[int, int]
        :return: Cell
        """
        # first try to return an existing cell
        cell_key = repr(sheet), position
        try:
            cell = Cell._all_cells[cell_key]
        except KeyError:
            # if cell does not exist, create it
            Cell._all_cells[cell_key] = cell = \
                Office.get_cell_class()(sheet, position)
        return cell

    def set_color(self, color: int or list or tuple or Color) -> None:
        """
        Sets color in cell to that passed as
        integer (as in a color hex code),
        list or tuple (containing r,g,b values)
        or a Color obj.
        :param color: int, list, tuple, or Color
        :return: None
        """
        raise NotImplementedError

    def get_color(self) -> int:
        """
        Gets color contained in cell as an integer.
        :return: int
        """
        raise NotImplementedError

    def remove_whitespace(self) -> None:
        """
        Edits cell value to remove tab, linefeed, return, form-feed,
        and vertical tab characters.
        :return: None
        """
        self.value = self.value_without_whitespace

    def clear(self):
        """Clears cell by setting value to None and color to default"""
        self.value = None
        self.set_color(DEFAULT_COLOR)

    @property
    def row(self) -> Row:
        return self.sheet.get_row(self.y)

    @property
    def column(self) -> Column:
        return self.sheet.get_column(self.x)

    @property
    def has_whitespace(self) -> bool:
        """
        Gets bool of whether cell string contains whitespace.
        If cell contains a number, returns False.
        :return: bool
        """
        return self.value_without_whitespace != self.value

    @property
    def value_without_whitespace(self) -> str:
        """
        Gets value of cell without whitespace.
        If cell is not a string, returns value unchanged.
        :return:
        """
        if isinstance(self.value, str):
            return ' '.join(self.value.split())
        else:
            return self.value

    @property
    def value(self) -> int or float or str or None:
        """
        Gets value contained in sheet cell.
        Does not return only number values.
        :return: int, float, str, or None
        """
        raise NotImplementedError

    @value.setter
    def value(self, new_value: str or int or float or None) -> None:
        """
        Sets cell value.
        :param new_value: str, int, float, or None
        :return: None
        """
        raise NotImplementedError

    @property
    def string(self) -> str:
        """
        Gets string value of cell.
        If stored value is str, returns str as is. Otherwise gets
        string of stored value, or empty string if None.
        :return: str
        """
        raise NotImplementedError

    @string.setter
    def string(self, new_string: str) -> None:
        """
        Sets string value of cell
        :param new_string: str
        :return: None
        """
        raise NotImplementedError

    @property
    def float(self):
        """
        Gets float value of cell.
        If cell contains a string or None, returns 0.
        :return: float
        """
        raise NotImplementedError

    @float.setter
    def float(self, new_float: int or float) -> None:
        """
        Sets float value of cell.
        :param new_float: int or float
        :return:
        """
        raise NotImplementedError

    @property
    def x(self) -> int:
        """
        Gets x position of cell
        :return: int
        """
        return self.position[0]

    @property
    def y(self) -> int:
        """
        Gets y position of cell
        :return: int
        """
        return self.position[1]

    @property
    def parents(self):
        """
        Returns generator iterating over parent instances.
        In the case of Cell this means row, column, sheet instances
        :return: Generator[WorkBookComponent]
        """
        yield self.row
        yield self.column
        yield self.sheet

    @property
    def instantiated_parents(self):
        """
        Returns parents of this cell that have been instantiated.
        This method was written for the purpose of clearing parent
        caches.
        :return: Generator[WorkBookComponent]
        """
        # yield row
        if Row.exists(self.sheet, self.y):
            yield self.row
        if Column.exists(self.sheet, self.x):
            yield self.row
        yield self.sheet

    def __repr__(self) -> str:
        """
        Gets cell repr with sheet, position, and value
        :return: str
        """
        return 'Cell(%s, %s) Value: %s' % (
            self.sheet, self.position, self.value.__repr__()
        )

    def __str__(self) -> str:
        return 'Cell[%s, Value: %s]' % (self.position, self.value.__repr__())


class CellLine:
    """
    Generator iterator that returns cells of a particular row or column
    """
    sheet = None
    axis = None
    index = None
    i = 0
    highest_inhabited_i = -1

    # max_i = 0

    def __init__(self, sheet: Sheet, axis: str, index: int) -> None:
        assert axis in ('x', 'y')
        if not isinstance(sheet, Sheet):
            raise TypeError('CellLine Constructor sheet arg should be a Sheet.'
                            ' Got instead: %s' % sheet.__repr__())
        if not isinstance(index, int):
            raise TypeError('CellLine __init__ index arg should be int. Got: '
                            '%s' % index.__repr__())
        self.sheet = sheet
        self.axis = axis
        self.index = index

    def __iter__(self):
        return self

    def __next__(self) -> 'Cell':
        # set starting x, y values
        x, y = (self.index, self.i) if self.axis == 'y' else \
            (self.i, self.index)
        cell = self.sheet.get_cell((x, y))  # get first cell
        # if cell is empty, look to see if a cell with a value follows.
        if cell.string == '' and self.i > self.highest_inhabited_i:
            for i in range(1, MAX_CELL_GAP):
                test_x, test_y = (self.index, self.i + i) if \
                    self.axis == 'y' else (self.i + i, self.index)
                test_cell = self.sheet.get_cell((test_x, test_y))
                if test_cell.string != '':
                    # if there is, mark that index as the highest i searched
                    # and break.
                    self.highest_inhabited_i = self.i + i
                    break
            else:
                # otherwise end iteration
                raise StopIteration()
        self.i += 1
        return cell


class Interface:
    """Abstract class inherited from by XW and Uno interfaces."""

    class Model:
        pass

    class Sheet:
        pass

    class Line:
        pass

    class Column:
        pass

    class Row:
        pass

    class Cell:
        pass


class Office:
    """
    Handles interface with workbook.

    This may not need to be a class, but any independent functions appear
    as their own macro, so this is instead its own class
    """

    class XW(Interface):
        """
        Handles XLWings interfacing with Office program
        """

        class Model(Model):
            """
            XW data model, extends Model superclass
            """
            def __init__(self, app_=None):
                if app_:
                    self.active_app = app_
                else:
                    try:
                        self.active_app = xw.apps[0]  # get first app open
                    except IndexError:
                        raise EnvironmentError(
                            'Office does not appear to have any running '
                            'instances.'
                        )
                # there should be only one open at a given time usually,
                # if any.

            def sheet_exists(self, *sheet_name: str) -> str:
                """
                Tests if sheet exists in any book.
                May be passed multiple sheet names.
                Returns first passed name that exists in books, or None
                :param sheet_name: str
                :return: str
                """
                for sheet_name_ in sheet_name:
                    if "::" in sheet_name_:
                        # if book/sheet name separator is in sheet_name,
                        # first find the book, then sheet
                        book_name, sheet_name_ = sheet_name_.split("::")
                        try:
                            book = self.active_app.books[book_name]
                            sheet = book.sheets[sheet_name_]
                        except KeyError:
                            continue
                        else:
                            assert sheet.name == sheet_name_
                            return sheet_name_
                    else:
                        # otherwise just find the sheet name
                        for sheet in self._xw_sheets:
                            if sheet_name_ == sheet.name:
                                return sheet_name_

            def __getitem__(self, item: str or int):
                """
                Gets passed item, returning the sheet of that name.
                :param item:
                :return: Sheet
                """
                if isinstance(item, str) and "::" in item:
                    # split and find book + name
                    book_name, sheet_name = item.split("::")
                    return Office.XW.Sheet(
                        self.active_app.books[book_name].sheets[sheet_name]
                    )
                else:
                    # otherwise just look everywhere
                    for sheet in self._xw_sheets:
                        if sheet.name == item:
                            return Office.XW.Sheet(
                                sheet
                            )

            @property
            def books(self):
                """
                Returns dict? of books open
                :return: dict? of books.
                """
                return self.active_app.books

            @property
            def _xw_sheets(self):
                """
                Yields each found xw sheet object in model
                :return: XW Sheet iterator
                """
                for xw_book in self.books:
                    for xw_sheet in xw_book.sheets:
                        yield xw_sheet

            @property
            def sheets(self):
                """
                Generator returning each sheet in Model.
                Weird implementation here to make it align with
                PyUno interface. This returns all sheets in all
                books open.
                :return: Sheet
                """
                for xw_sheet in self._xw_sheets:
                    yield Office.XW.Sheet(xw_sheet)

            @property
            def sheet_names(self):
                """
                Gets iterable of names of usable sheets in Model
                :return: iterator
                """
                for book in self.books:
                    for sheet in book.sheets:
                        yield "%s::%s" % (book.name, sheet.name)

        class Sheet(Sheet):
            """
            XW Sheet
            """
            def __init__(
                    self,
                    xw_sheet,
                    reference_row_index=0,
                    reference_column_index=0
            ) -> None:
                super().__init__(
                    i7e_sheet=xw_sheet,
                    reference_column_index=reference_column_index,
                    reference_row_index=reference_row_index
                )

            @property
            def screen_updating(self) -> None:
                return self.i7e_sheet.book.app.screen_updating

            @screen_updating.setter
            def screen_updating(self, new_bool: bool) -> None:
                self.i7e_sheet.book.app.screen_updating = new_bool

            @Sheet.enduring_cache
            def __str__(self) -> str:
                return 'Sheet[%s::%s]' % (
                    self.i7e_sheet.name,
                    self.i7e_sheet.book.name,
                )

            @Sheet.enduring_cache  # this Sheet's repr should not change
            def __repr__(self) -> str:
                return 'Sheet[%s::%s]' % (
                    self.i7e_sheet.name,
                    self.i7e_sheet.book.fullname,
                )

        class Line(Line):
            """
            XW Line
            """
            pass  # no methods defined here at this time.
            # keeping for MR0 purposes

        class Column(Line, Column):
            """
            XW Column
            """
            def __init__(
                    self,
                    sheet: Sheet,
                    column_index: int,
                    reference_column_index: int=0):
                super().__init__(
                    sheet=sheet,
                    index=column_index,
                    reference_index=reference_column_index
                )

            def __iter__(self):
                return self.get_iterator(axis='y')

        class Row(Line, Row):
            """
            XW Row
            """
            def __init__(
                    self,
                    sheet: Sheet,
                    row_index: int,
                    reference_row_index: int=0
            ) -> None:
                super().__init__(
                    sheet=sheet,
                    index=row_index,
                    reference_index=reference_row_index,
                )

            def __iter__(self):
                return self.get_iterator(axis='x')

        class Cell(Cell):
            """
            XW Cell
            """

            def set_color(self, color: int or list or tuple) -> None:
                if color >= 0:
                    color = Color(color)
                    self._range.color = color.rgb
                elif color == -1:
                    self._range.color = None

            def get_color(self) -> int:
                color_int = self._range.color
                if color_int is None:
                    color_int = -1
                return color_int

            @property
            def _range(self):
                """
                Gets XW Range obj for this cell
                :return: xlwings.Range
                """
                x, y = self.position
                x += 1
                y += 1  # correct to excel 1 based index
                # XW passes position tuples as row, column
                return self.sheet.i7e_sheet.range(y, x)

            @property
            @Cell.value_cache
            def value(self) -> int or float or str or None:
                return self._range.value

            @value.setter
            @Cell.clear_cache
            def value(self, new_value) -> None:
                self._range.value = new_value

            @property
            @Cell.value_cache
            def float(self):
                # XW will only return number (float), str or None in most
                # cases, others include Date, (etc)?
                if isinstance(self.value, float):
                    return self.value
                else:
                    return 0.

            @property
            @Cell.value_cache
            def string(self):
                if self.value is not None:
                    string = str(self.value)
                    # remove unneeded digits
                    if isinstance(self.value, float) and string[-2:] == '.0':
                        string = string[:-2]
                    return string
                else:
                    return ''

    class Uno(Interface):
        """
        Handles Uno interfacing with Office program
        """

        class Model(Model):
            """
            Handles usages of PyUno Model
            """

            def __init__(self) -> None:
                # not an error; provided by macro caller
                # noinspection PyUnresolvedReferences
                desktop = XSCRIPTCONTEXT.getDesktop()
                py_uno_model = desktop.getCurrentComponent()
                if not hasattr(py_uno_model, 'Sheets'):
                    raise AttributeError(
                        'Model does not have Sheets. '
                        'This macro needs to be run from a calc workbook.'
                    )
                self.model = py_uno_model

            def __getitem__(self, item: str or int) -> Sheet:
                """
                Gets identified sheet.
                :param item: str or int
                :return: Sheet
                """
                assert isinstance(item, (str, int))
                # try to get appropriate sheet from uno model.
                # If sheet index or name cannot be found, raise a more
                # readable error message than the terribly unhelpful
                # uno message.
                if isinstance(item, int):
                    try:
                        return Office.Uno.Sheet(
                            self.model.Sheets.getByIndex(item))
                    except:  # can't seem to put the actual exception
                        # class here
                        raise IndexError('Could not retrieve sheet at index'
                                         '%s' % repr(item))
                else:
                    try:
                        return Office.Uno.Sheet(
                            self.model.Sheets.getByName(item))
                    except:
                        raise KeyError('Could not retrieve sheet with name %s'
                                       % repr(item))

            def sheet_exists(self, *args: str) -> str:
                """
                Checks each string passed as arg to see if it exists as a
                sheet name. If so, returns it, otherwise, moves to the next
                :param args: strings
                :return: str of first viable sheet name or None if no
                viable name is found
                """
                assert all([isinstance(arg, str) for arg in args])
                for sheet_name in args:
                    try:
                        self.model.Sheets.getByName(sheet_name)
                    except:  # todo: find actual exception class
                        pass
                    else:
                        return sheet_name

            @property
            def sheets(self):
                """
                Generator returning each sheet in Model / Book
                :return: Sheet
                """
                i = 0
                while True:  # loop until break
                    try:
                        yield Office.Uno.Sheet(self.model.Sheets.getByIndex(i))
                    except:
                        break
                    else:
                        i += 1

            @property
            def sheet_names(self):
                """
                Returns tuple of sheet names in model / current book
                :return: tuple
                """
                return self.model.Sheets.ElementNames

        class Sheet(Sheet):
            """
            Handles usage of a single Uno workbook sheet
            """

            def __init__(
                    self,
                    uno_sheet,
                    reference_row_index=0,
                    reference_column_index=0
            ) -> None:
                super().__init__(
                    i7e_sheet=uno_sheet,
                    reference_row_index=reference_row_index,
                    reference_column_index=reference_column_index
                )

        class Line(Line):
            pass  # no methods defined here anymore,
            # keeping this in place for MRO purposes

        class Column(Line, Column):
            """
            Handles usage of a column within a sheet
            """
            def __init__(
                    self,
                    sheet: Sheet,
                    column_index: int,
                    reference_column_index: int=0):
                super().__init__(
                    sheet=sheet,
                    index=column_index,
                    reference_index=reference_column_index
                )

            def __iter__(self):
                """
                Returns iterable line of cells
                :return: Iterable
                """
                return self.get_iterator(axis='y')

        class Row(Line, Row):
            """
            Handles usage of a row within a sheet
            """

            def __init__(
                    self,
                    sheet: Sheet,
                    row_index: int,
                    reference_row_index: int=0
            ) -> None:
                super().__init__(
                    sheet=sheet,
                    index=row_index,
                    reference_index=reference_row_index,
                )

            def __iter__(self):
                return self.get_iterator(axis='x')

        class Cell(Cell):
            """
            Handles usage of an individual cell
            """
            def set_color(self, color):
                """
                Sets cell background color
                :param color: int, list or tuple
                """
                assert isinstance(color, (int, tuple, list))
                if isinstance(color, int):
                    color_int = color
                else:
                    color_int = color[0] * 256 ** 2 + color[1] * 256 + color[2]
                self._source_cell.CellBackColor = color_int

            def get_color(self) -> int:
                return self._source_cell.CellBackColor

            @property
            def _uno_sheet(self):
                """
                Gets uno Sheet obj.
                :return: uno Sheet obj
                """
                return self.sheet.i7e_sheet

            @property
            def _source_cell(self):
                """
                Gets PyUno cell from which values are drawn
                :return:
                """
                return self._uno_sheet.getCellByPosition(*self.position)

            @property
            @Cell.value_cache
            def value(self) -> int or float or str:
                """
                Gets value of cell.
                :return: str or float
                """
                # get cell value type after formula evaluation has been
                # carried out. This will return the cell value's type
                # even if it is not a formula
                t = self._source_cell.FormulaResultType.value
                if t == 'TEXT':
                    return self._source_cell.getString()
                elif t == 'VALUE':
                    return self._source_cell.getValue()

            @value.setter
            @Cell.clear_cache
            def value(self, new_value: int or float or str) -> None:
                """
                Sets source cell string and number value appropriately for
                a new value.
                This does not handle formulas at the present time.
                :param new_value: int, float, or str
                """
                assert isinstance(new_value, (str, int, float))
                if isinstance(new_value, str):
                    self.string = new_value
                else:
                    self.float = new_value

            @property
            @Cell.value_cache
            def string(self) -> str:
                """
                Returns string value directly from source cell
                :return: str
                """
                return self._source_cell.getString()

            @string.setter
            @Cell.clear_cache
            def string(self, new_string: str) -> None:
                """
                Sets string value of source cell directly
                :param new_string: str
                """
                assert isinstance(new_string, str)
                self._source_cell.setString(new_string)

            @property
            @Cell.value_cache
            def float(self) -> float:
                """
                Returns float value directly from source cell 'value'
                :return: float
                """
                return self._source_cell.getValue()

            @float.setter
            @Cell.clear_cache
            def float(self, new_float: int or float) -> None:
                """
                Sets float value of source cell directly
                :param new_float: int or float
                :return: None
                """
                assert isinstance(new_float, (int, float))
                new_value = float(new_float)
                self._source_cell.setValue(new_value)

    @staticmethod
    def get_interface() -> str or None:
        """
        Test for what interface is using this macro, and return the string
        of the appropriate class that should be used.
        :return: str or None if no interface can be determined
        """
        # test for Python Uno
        try:
            XSCRIPTCONTEXT  # if this variable exists, PyUno is being used.
        except NameError:
            pass
        else:
            return 'Uno'

        if xw is not None:
            return 'XW'

        # otherwise, return None / False

    @staticmethod
    def get_interface_class() -> Interface:
        """Gets interface class, ie, Uno or XW"""
        interface = Office.get_interface()  # gets str name of interface class
        if not interface:
            raise ValueError('Should be run as macro using XLWings or PyUno.'
                             'Neither could be detected.')
        return getattr(Office, interface)

    @staticmethod
    def get_model() -> Model:
        return Office.get_model_class()()  # get model class and instantiate

    @staticmethod
    def get_model_class() -> type:
        """Gets appropriate Model class"""
        return Office.get_interface_class().Model

    @staticmethod
    def get_sheet_class() -> type:
        """Gets appropriate Sheet class"""
        return Office.get_interface_class().Sheet

    @staticmethod
    def get_column_class() -> type:
        """Gets appropriate Column class"""
        return Office.get_interface_class().Column

    @staticmethod
    def get_row_class() -> type:
        """Gets appropriate Row class"""
        return Office.get_interface_class().Row

    @staticmethod
    def get_cell_class() -> type:
        """Gets appropriate Cell class"""
        return Office.get_interface_class().Cell


###############################################################################
# Column Data


class Translation:
    """
    Handles movement of data from source to target sheets and applies
    modifications
    """
    _whitespace_action = WHITESPACE_HIGHLIGHT_STR
    _duplicate_action = DUPLICATE_HIGHLIGHT_STR

    def __init__(
            self,
            dialog_parent,
            source_sheet: Sheet,
            target_sheet: Sheet,
            column_translations=None,
            source_start_row=1,
            target_start_row=1,
            whitespace_action=WHITESPACE_HIGHLIGHT_STR,
            duplicate_action=DUPLICATE_HIGHLIGHT_STR,
            read_log: bool=False,
            write_log: bool=False,
            log_group: str=None,
    ):

        if not isinstance(source_sheet, Sheet):
            raise TypeError('Source sheet should be a Sheet, got: %s'
                            % repr(source_sheet))
        if not isinstance(target_sheet, Sheet):
            raise TypeError('Target sheet should be a Sheet, got: %s'
                            % repr(source_sheet))
        self._dialog_parent = dialog_parent
        self._source_sheet = source_sheet
        self._target_sheet = target_sheet
        self._row_deletions = set()
        self._src_cell_transforms = {}
        self._tgt_cell_transforms = {}
        self._source_start_row = source_start_row
        self._target_start_row = target_start_row
        self._whitespace_action = whitespace_action
        self._duplicate_action = duplicate_action
        self.read_log = read_log
        self.write_log = write_log
        self.log_group = log_group
        self.row_log = RowLog(OS.get_log_dir_path()) if \
            read_log or write_log else None
        # create column translations from passed list of dicts
        # in settings
        self._column_translations = []
        self.add_column_translation(*column_translations)

        self.translation_rows = {}  # y_index: set(x_indices)
        self.cell_translation_generators = []  # x_index: generator
        self.cell_translations = {}  # src_pos: CellTranslation

        self._get_cell_generators()
        self._generate_cell_translations()

        if self.duplicate_action == DUPLICATE_HIGHLIGHT_STR:
            self._highlight_translation_rows_with_duplicates()
        elif self.duplicate_action == DUPLICATE_REMOVE_ROW_STR:
            self._remove_translation_rows_with_duplicates()

        if self.whitespace_action == WHITESPACE_HIGHLIGHT_STR:
            self._highlight_translation_rows_with_whitespace()
        elif self.whitespace_action == WHITESPACE_REMOVE_STR:
            self._remove_whitespace_in_translation_rows()

    def commit(self):
        try:
            print('committing translations')
            self.source_sheet.screen_updating = False
            self.target_sheet.screen_updating = False
            self.clear_target()
            self._apply_translation_rows()
            if self.write_log:  # write log if that setting is set by user.
                self.row_log.make_log(self.log_group, self.target_sheet)
        finally:
            self.source_sheet.screen_updating = True
            self.target_sheet.screen_updating = True

    def _apply_translation_rows(self):
        for y in self.translation_rows:
            t_row = self.translation_rows[y]
            assert isinstance(t_row, TranslationRow)
            t_row.apply(self.target_sheet, y)

    def _get_cell_generators(self):
        for column_translation in self.column_translations:
            assert isinstance(column_translation, ColumnTranslation)
            self.cell_translation_generators.append(
                column_translation.get_generator())

    def _generate_cell_translations(self):
        print('mapping row translations')
        y = self._source_start_row
        while any([generator.has_next() for generator in
                   self.cell_translation_generators]):
            row = TranslationRow()
            for generator in self.cell_translation_generators:
                assert isinstance(generator, CellGenerator)
                if not generator.has_next():
                    continue
                cell_translation = generator.next()
                self.cell_translations[cell_translation.src_pos] = \
                    cell_translation
                row.add_cell_translation(cell_translation)
            self.translation_rows[y] = row
            y += 1
        print('done mapping row translations')

    def _highlight_translation_rows_with_whitespace(self):
        whitespace_positions = list(self.get_whitespace_positions())
        assert isinstance(whitespace_positions, list)
        for item in whitespace_positions:
            assert isinstance(item, tuple), 'got: %s' % item
            assert len(item) == 2, 'got: %s' % item
        for pos in whitespace_positions:
            try:
                cell_t = self.cell_translations[pos]
            except KeyError:
                continue
            assert isinstance(cell_t, CellTranslation)
            row = cell_t.row
            assert isinstance(row, TranslationRow)
            row.color_cell_and_row(
                pos[0],
                WHITESPACE_CELL_COLOR,
                WHITESPACE_ROW_COLOR,
            )
        self._whitespace_feedback(whitespace_positions)

    def _remove_whitespace_in_translation_rows(self):
        whitespace_positions = list(self.get_whitespace_positions())
        for pos in whitespace_positions:
            try:
                cell_t = self.cell_translations[pos]
                assert isinstance(cell_t, CellTranslation)
                cell_t.add_transform(lambda cell: cell.remove_whitespace())
            except KeyError:
                continue
        self._whitespace_feedback(whitespace_positions)

    def _highlight_translation_rows_with_duplicates(self):
        duplicate_positions = list(self.get_duplicate_positions())
        for pos in duplicate_positions:
            try:
                cell_t = self.cell_translations[pos]
            except KeyError:
                continue
            assert isinstance(cell_t, CellTranslation)
            row = cell_t.row
            assert isinstance(row, TranslationRow)
            row.color_cell_and_row(
                pos[0],
                DUPLICATE_CELL_COLOR,
                DUPLICATE_ROW_COLOR
            )
        self._duplicates_feedback(duplicate_positions)

    def _remove_translation_rows_with_duplicates(self):
        duplicate_positions = list(self.get_duplicate_positions())
        for pos in duplicate_positions:
            try:
                cell_t = self.cell_translations[pos]
            except KeyError:
                continue
            row = cell_t.row
            for y in self.translation_rows:
                if self.translation_rows[y] is row:
                    del self.translation_rows[y]
                    break
        self._duplicates_feedback(duplicate_positions)

    def get_duplicate_positions(self):
        """
        Returns lists of tuples of positions
        :return: iterator of tuples
        """
        print('looking for duplicate cells')
        for column_translation in self._column_translations:
            assert isinstance(column_translation, ColumnTranslation)
            if not column_translation.check_for_duplicates:
                continue
            for duplicate_cell in \
                    column_translation.get_duplicate_source_cells():
                assert isinstance(duplicate_cell, Cell)
                yield duplicate_cell.position
        print('done looking for duplicates')

    def get_whitespace_positions(self):
        """
        Returns lists of tuples of positions
        :return: iterator of tuples
        """
        print('looking for whitespace in cells')
        for column_translation in self._column_translations:
            assert isinstance(column_translation, ColumnTranslation)
            if not column_translation.check_for_whitespace:
                continue
            for cell in column_translation.get_whitespace_source_cells():
                yield cell.position
        print('done looking for whitespace')

    def _confirm_overwrite(self):
        reply = QMessageBox.question(
            self._dialog_parent,
            'Overwrite Cells?',
            'Cells on the target sheet will be overwritten.\n'
            'Proceed?',
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel
        )
        return reply == QMessageBox.Yes

    def add_column_translation(self, *args, **kwargs) -> None:
        """
        Adds translation to queue which when applied, copies cell data
        from source column to target column.
        source and target columns may be identified either by passing
        the name of that column, as determined by the sheet's reference
        row, or by their index.
        An index or name must be passed for both source and target
        columns, however passing both an index and a name will result
        in a ValueError being raised.
        If passed kwargs, will pass on those to a
        created ColumnTranslation obj.
        If passed a dictionary or dictionaries, will add one
        ColumnTranslation for each of those dictionaries, and pass it
        the contained kwargs.
            source_column_i: int
            source_column_name: int, float, or str
            target_column_i: int
            target_column_name: int, float, or str
            kwargs: other kwargs will be passed to created
        ColumnTranslation.
        :param args: ColumnTranslation kwargs dictionaries
        :param kwargs: kwargs for a single ColumnTranslation.
        """
        # check that passed args are all dictionaries
        assert all([isinstance(item, dict) for item in args]), \
            'passed args must be dictionaries of kwargs for ' \
            'ColumnTranslation. Instead got %s' % args
        # for each passed kwargs dictionary,
        # including that passed to this method;
        for kwargs_dict in args + (kwargs,) if kwargs else args:
            # ensure correct kwargs were passed.
            # Exactly one source column identifier should have been
            # passed for each of src col and tgt col
            source_column_i = kwargs_dict.get(SOURCE_COLUMN_INDEX_KEY, None)
            source_column_name = kwargs_dict.get(SOURCE_COLUMN_NAME_KEY, None)
            target_column_i = kwargs_dict.get(TARGET_COLUMN_INDEX_KEY, None)
            target_column_name = kwargs_dict.get(TARGET_COLUMN_NAME_KEY, None)
            # if source is null, continue
            if source_column_i == -1 or source_column_name == NONE_STRING:
                continue
            if bool(source_column_i) == bool(source_column_name):
                raise ValueError(
                    'One of source_column_i or source_column_name must '
                    'be passed, but not both. Got %s and %s respectively'
                    % (source_column_i, source_column_name)
                )
            if bool(target_column_i) == bool(target_column_name):
                raise ValueError(
                    'One of target_column_i or target_column_name must '
                    'be passed, but not both. Got %s and %s respectively'
                    % (target_column_i, target_column_name)
                )
            # add ColumnTranslation
            self._column_translations.append(
                ColumnTranslation(
                    parent_translation=self,
                    **kwargs_dict
                )
            )

    def clear_target(self):
        """
        Clears target sheet of conflicting cell data
        Raises dialog for user to ok if anything is to be deleted.
        """
        user_ok = False  # whether user has been presented with dialog
        for column in self._target_sheet.columns:
            assert isinstance(column, Column)
            for cell in column:
                if cell.y < self._target_start_row:
                    continue
                if not user_ok and cell.value != '':
                    # if user has not yet ok'd deletion of cells:
                    if self._confirm_overwrite:
                        print('confirm dlg')
                        proceed = self._confirm_overwrite()
                        if not proceed:
                            return False
                    user_ok = True
                cell.value = ''
                cell.set_color(DEFAULT_COLOR)

    def _whitespace_feedback(self, whitespace_positions):
        """
        Reports to user on whitespace removals.
        Written to be called by _add_whitespace_cell_transforms method
        after whitespace transforms have been added.
        :param whitespace_positions:
        """
        if not whitespace_positions:
            return
        print('giving whitespace feedback')
        secondary_string = ''
        if self.whitespace_action == WHITESPACE_REMOVE_STR:
            secondary_string = (
                'Cell values were edited to remove '
                'unneeded '
                'tab, linefeed, return, formfeed, '
                'and/or vertical tab characters.')
        elif self.whitespace_action == WHITESPACE_HIGHLIGHT_STR:
            secondary_string = (
                '%s Cell values were highlighted in '
                'checked '
                'columns' % len(whitespace_positions))
        InfoMessage(
            parent=self._dialog_parent,
            title='Whitespace Found',
            main='Whitespace found in %s cells' % len(
                whitespace_positions),
            secondary=secondary_string,
            detail=self._position_report(*whitespace_positions)
        )

    def _duplicates_feedback(
            self,
            duplicate_positions
    ) -> None:
        """
        Provides feedback to user about duplicates and actions taken
        regarding said duplicates.
        :param duplicate_positions: iterable of duplicate_positions
        """
        if not duplicate_positions or \
                self.duplicate_action == DUPLICATE_IGNORE_STR:
            return
        print('giving duplicates feedback')
        secondary_string = ''
        if self.duplicate_action == DUPLICATE_HIGHLIGHT_STR:
            secondary_string = '%s Cell values were highlighted in ' \
                               'checked columns' % len(duplicate_positions)
        elif self.duplicate_action == DUPLICATE_REMOVE_ROW_STR:
            n_rows_w_duplicates = len(set(
                [pos[1] for pos in duplicate_positions]))
            secondary_string = '%s Cell rows containing duplicate ' \
                               'values were removed' % n_rows_w_duplicates
        InfoMessage(
            parent=self._dialog_parent,
            title='Duplicate Values',
            main='%s Duplicate cell values found' % len(duplicate_positions),
            secondary=secondary_string,
            detail=self._position_report(*duplicate_positions)
        )

    def _position_report(self, *src_positions):
        """
        Converts iterable of positions into a more user-friendly
        report.
        output should consist of a list of row numbers, each with
        the names of the column containing passed position
        :param positions: tuples (int x, int y)
        :return: str
        """

        rows = []  # list of row indices in report.
        # This keeps the columns in order.
        row_columns = {}  # dictionary of string lists
        for x, y in src_positions:
            column_name = self._source_sheet.get_column(x).name
            y += 1  # convert to office 1-base index
            if y not in rows:
                row_columns[y] = list()
                rows.append(y)
            row_columns[y].append(column_name)
        # now make the report
        row_strings = [
            'Row %s; %s' % (y, ', '.join(row_columns[y]))
            for y in rows]
        return '\n'.join(row_strings)

    @property
    def source_sheet(self):
        """
        Gets source sheet
        :return: Sheet
        """
        return self._source_sheet

    @property
    def target_sheet(self):
        """
        Gets target sheet
        :return: Sheet
        """
        return self._target_sheet

    @property
    def source_start_row(self):
        """
        Sets the row index at which cells begin to be copied.
        0 is first row
        :return: int
        """
        return self._source_start_row

    @source_start_row.setter
    def source_start_row(self, new_index):
        """
        Sets the row index at which cells begin to be copied
        :param new_index: int
        """
        assert isinstance(new_index, int)
        self._source_start_row = new_index

    @property
    def target_start_row(self):
        """
        Gets the row index at which cells begin to be written to
        :return: int
        """
        return self._target_start_row

    @target_start_row.setter
    def target_start_row(self, new_index):
        """
        Sets the row index at which cells begin to be written to
        :param new_index: int
        """
        assert isinstance(new_index, int)
        self._target_start_row = new_index

    @property
    def column_translations(self):
        """
        Returns list of column translations
        :return: list of ColumnTranslations
        """
        return self._column_translations.copy()

    @property
    def row_deletions(self) -> set:
        """
        Gets set of rows to be deleted in translation
        :return: set
        """
        return self._row_deletions.copy()

    @property
    def whitespace_action(self):
        """
        Gets name of action that will be taken for cells containing
        whitespace
        :return: str
        """
        return self._whitespace_action

    @whitespace_action.setter
    def whitespace_action(self, action):
        """
        Sets action to be taken when cell contains whitespace
        :param action: str
        """
        assert action in (
            WHITESPACE_REMOVE_STR,
            WHITESPACE_HIGHLIGHT_STR,
            WHITESPACE_IGNORE_STR
        )
        self._whitespace_action = action

    @property
    def duplicate_action(self):
        """
        Gets name of action that will be taken for rows containing
        duplicates
        :return: str
        """
        return self._duplicate_action

    @duplicate_action.setter
    def duplicate_action(self, action):
        """
        Sets name of action that will be taken for rows
        containing duplicates
        :param action: str
        """
        assert action in (
            DUPLICATE_REMOVE_ROW_STR,
            DUPLICATE_HIGHLIGHT_STR,
            DUPLICATE_IGNORE_STR
        )
        self._duplicate_action = action

    @property
    def src_cell_transforms(self):
        """
        Gets cell transforms that are to be applied based on src
        sheet position.
        :return: dict{src_sheet_position: list[function]}
        """
        return self._src_cell_transforms.copy()

    @property
    def tgt_cell_transforms(self):
        """
        Gets cell transforms that are to be applied based on tgt
        sheet position
        :return: dict{tgt_sheet_position: list[function]}
        """
        return self._tgt_cell_transforms.copy()


class ColumnTranslation:
    """
    Handles movement and modification of a column
    Applies translation of individual column
    """

    def __init__(
            self,
            parent_translation: Translation,
            source_column_i=None,
            target_column_i=None,
            source_column_name=None,
            target_column_name=None,
            check_for_whitespace: bool=True,
            check_for_duplicates: bool=False) -> None:
        if (
            bool(source_column_i is None) ==
            bool(source_column_name is None)
        ):
            raise ValueError(
                'Source column index or name must be passed, but not both. '
                'Got args source_column_i: %s (%s) and source_column_name: %s'
                ' (%s) respectively'
                % (source_column_i, source_column_i.__class__.__name__,
                   source_column_name, source_column_name.__class__.__name__))
        if (
            bool(target_column_i is None) ==
            bool(target_column_name is None)
        ):
            raise ValueError(
                'Target column index or name must be passed, but not both. '
                'Got args target_column_i: %s (%s) and target_column_name: %s'
                '(%s)'
                % (target_column_i, target_column_i.__class__.__name__,
                   target_column_name, target_column_name.__class__.__name__)
            )
        self._parent_translation = parent_translation
        self._target_column_i = target_column_i
        self._source_column_i = source_column_i
        self._target_column_name = target_column_name
        self._source_column_name = source_column_name
        self._duplicates_check = check_for_duplicates
        self._whitespace_check = check_for_whitespace

    def get_generator(self):
        return CellGenerator(
            src_col=self.source_column,
            tgt_col=self.target_column,
            start_index=self._parent_translation.source_start_row
        )

    # source sheet getters / setters

    @property
    def source_sheet(self) -> Sheet:
        """
        Gets source sheet, from which cells are retrieved
        :return: Sheet
        """
        return self._parent_translation.source_sheet

    @property
    def source_column_i(self) -> int:
        """
        Gets source column identifier
        :return: int
        """
        if self._source_column_i is not None:
            return self._source_column_i
        else:
            return self.source_column.index

    @source_column_i.setter
    def source_column_i(self, new_column: int):
        """
        Sets source column
        :param new_column: int
        """
        assert isinstance(new_column, int)
        self._source_column_i = new_column
        self._source_column_name = None

    @property
    def source_column_name(self) -> int or str or float or None:
        """
        Gets name by which the source column is identified.
        If the source column is identified by index, will return None
        :return: int, float, str, or None
        """
        if self._source_column_name is not None:
            return self._source_column_name
        else:
            return self.source_column.name

    @source_column_name.setter
    def source_column_name(self, new_column_name) -> None:
        """
        Sets name by which source column will be identified
        :param new_column_name: int, float or str
        :return: None
        """
        assert isinstance(new_column_name, (int, float, str))
        if new_column_name not in self.source_sheet.columns.names:
            raise ValueError('Passed column name %s not found in source sheet'
                             % new_column_name)
        self._source_column_name = new_column_name
        self._source_column_i = None

    @property
    def source_column(self) -> Column:
        """
        Gets source column
        :return: Office.Column
        """
        if self._source_column_i is not None:
            identifier = self._source_column_i
        else:
            identifier = self._source_column_name
        return self.source_sheet.get_column(identifier)

    # target sheet getters/setters

    @property
    def target_sheet(self):
        """
        Gets target sheet, to which cells are moved
        :return: Sheet
        """
        return self._parent_translation.target_sheet

    @property
    def target_column_i(self) -> int or None:
        """
        Gets target column index, if it is identified by index,
        or else None.
        :return: int or None
        """
        if self._target_column_i is not None:
            return self._target_column_i
        else:
            return self.target_column.index

    @target_column_i.setter
    def target_column_i(self, new_column):
        """
        Sets target column by passing an index by which to identify it.
        :param new_column: int or str
        """
        assert isinstance(new_column, int)
        self._target_column_i = new_column
        self._target_column_name = None

    @property
    def target_column_name(self):
        """
        Gets name by which target column is identified, or else None
        if Column is identified by index.
        :return: int, float, str, or None
        """
        if self._target_column_name is not None:
            return self._target_column_name
        else:
            return self.target_column.name

    @target_column_name.setter
    def target_column_name(self, new_name) -> None:
        """
        Sets name by which target will be identified
        :param new_name: int, float, or str
        :return: None
        """
        assert isinstance(new_name, (int, float, str))
        if new_name not in self.target_sheet.columns.names:
            raise ValueError('Column name %s not found in target sheet'
                             % new_name)
        self._target_column_name = new_name
        self._target_column_i = None

    @property
    def target_column(self) -> Column:
        """
        Gets target column
        :return: Office.Column
        """
        identifier = self._target_column_i if \
            self._target_column_i is not None else \
            self._target_column_name
        return self.target_sheet.get_column(identifier)

    # column translation options

    @property
    def check_for_duplicates(self) -> bool:
        """
        Returns bool of whether column should be checked for duplicates
        :return: bool
        """
        return self._duplicates_check

    @check_for_duplicates.setter
    def check_for_duplicates(self, new_bool: bool):
        """
        Sets bool of whether column should be checked for duplicates
        :param new_bool: bool
        """
        self._duplicates_check = new_bool

    @property
    def check_for_whitespace(self) -> bool:
        """
        Returns bool of whether column should be checked for whitespace
        :return: bool
        """
        return self._whitespace_check

    @check_for_whitespace.setter
    def check_for_whitespace(self, new_bool: bool):
        """
        Gets bool for whether column is checked for whitespace
        :param new_bool: bool
        """
        self._whitespace_check = new_bool

    def get_whitespace_source_cells(self):
        """
        Yields cells in source column which contain whitespace
        :return: iterator of cells
        """
        assert self._parent_translation is not None, \
            "Parent translation must be set"
        for cell in self.source_column:
            if cell.has_whitespace:
                yield cell

    def get_duplicate_source_cells(self):
        """
        Yields cells in source column with values that are duplicates of
        previously occurring values
        :return: iterator of cells
        """
        assert self._parent_translation is not None, \
            "Parent translation must be set"
        values = set()
        for cell in self.source_column:
            value = cell.value_without_whitespace
            # if cell's value is in set of existing values, return cell.
            if value in values:
                yield cell
            else:  # otherwise, check if cell is in log
                parent = self._parent_translation
                if parent.read_log:  # if option is set
                    parent.row_log.find_duplicates(
                        value, parent.log_group, self.target_column_name
                    )
                values.add(value)  # add value to set of existing values


class CellGenerator:
    def __init__(self, src_col, tgt_col, start_index):
        if not isinstance(src_col, Column):
            raise TypeError('expected Column. got: %s' % src_col)
        if not isinstance(tgt_col, Column):
            raise TypeError
        if not isinstance(start_index, int):
            raise TypeError
        self.tgt_col = tgt_col
        self.src_col = src_col
        self.i = start_index
        self.end_index_exclusive = len(src_col)

    def has_next(self):
        if self.i < self.end_index_exclusive:
            return True

    def next(self):
        cell_translation = CellTranslation(
            cell=self.src_col.get_cell_by_index(self.i),
            src_x=self.src_col.index,
            tgt_x=self.tgt_col.index
        )
        self.i += 1
        return cell_translation


class TranslationRow:
    def __init__(self):
        self.cell_translations = []

    def add_cell_translation(self, *translations):
        for cell_translation in translations:
            cell_translation.row = self
            self.cell_translations.append(cell_translation)

    def color_cell_and_row(self, cell_x, cell_color, row_color):
        for cell_t in self.cell_translations:
            assert isinstance(cell_t, CellTranslation)
            if cell_t.src_x != cell_x:
                cell_t.add_transform(
                    lambda cell:
                    cell.set_color(row_color) if
                    cell.get_color() == -1  # if cell is default color
                    else None
                )
            else:
                cell_t.add_transform(lambda cell: cell.set_color(cell_color))

    def apply(self, tgt_sheet, y):
        for cell_t in self.cell_translations:
            assert isinstance(cell_t, CellTranslation)
            cell_t.apply(tgt_sheet, y)


class CellTranslation:
    row = None

    def __init__(self, cell, src_x, tgt_x):
        self.cell, self.src_x, self.tgt_x = cell, src_x, tgt_x
        self.transforms = []

    def apply(self, tgt_sheet, y_pos):
        if not isinstance(tgt_sheet, Sheet):
            raise TypeError
        if not isinstance(y_pos, int):
            raise TypeError
        tgt_cell = tgt_sheet.get_cell((self.tgt_x, y_pos))
        tgt_cell.value = self.cell.value
        [transform(tgt_cell) for transform in self.transforms]

    def add_transform(self, transform):
        assert hasattr(transform, '__call__')
        self.transforms.append(transform)

    @property
    def src_pos(self):
        return self.cell.position


class CellTransform:
    def __init__(self, position, sheet, call_obj):
        assert all([isinstance(x, int) for x in position])
        assert sheet in ('src', 'tgt')
        assert hasattr(call_obj, '__call__')
        self.position = position
        self.sheet = sheet
        self.call_obj = call_obj

    def __call__(self, cell):
        self.call_obj(cell)


###############################################################################
# GUI elements

class PyLeadDlg(QDialog):
    """
    Abstract class inherited from by other dialogs
    """
    quit_flag = False

    def __init__(self, settings: dict) -> None:
        super().__init__()
        self._initial_settings = settings

    def finish(self) -> None:
        """
        method called when caller is done with dlg.
        :return: None
        """
        # inherited by child classes

    def closeEvent(self, event):
        print('closing macro')
        # noinspection PyArgumentList
        self.quit_flag = True

    @property
    def settings(self) -> dict:
        """
        Returns settings inputted by user in this dlg
        :return: dict
        """
        raise NotImplementedError


class TranslationDialog(PyLeadDlg):
    """
    Table widget containing columns and options to manipulate them
    """

    def __init__(self, settings):
        print('Translation Dlg began')
        super().__init__(settings)
        src_sheet_name = settings[SOURCE_SHEET_KEY]
        tgt_sheet_name = settings[TARGET_SHEET_KEY]
        source_start = settings[SOURCE_START_KEY]
        target_start = settings[TARGET_START_KEY]
        assert isinstance(src_sheet_name, (str, int, float))
        assert isinstance(tgt_sheet_name, (str, int, float))
        assert isinstance(source_start, int), source_start
        assert isinstance(target_start, int), target_start
        # get Sheet obj from name or index if needed
        source_sheet = model[src_sheet_name]
        target_sheet = model[tgt_sheet_name]
        assert isinstance(source_sheet, Sheet)
        assert isinstance(target_sheet, Sheet)
        source_sheet.reference_row_index = source_start - 1
        target_sheet.reference_row_index = target_start - 1
        # get integer from string indices if needed.
        # checking to ensure strings are convertible should have already
        # taken place.
        if not isinstance(source_start, int):
            source_start = int(source_start)
        if not isinstance(target_start, int):
            target_start = int(target_start)
        self.source_sheet = source_sheet  # sheet to retrieve data from
        self.target_sheet = target_sheet  # sheet to send data to
        self.source_start_row = source_start
        self.target_start_row = target_start
        self.setWindowTitle(APP_WINDOW_TITLE)

        self.table = self.TranslationTable(
            source_sheet=self.source_sheet,
            target_sheet=self.target_sheet,
            presets=settings.get(COLUMN_TRANSLATIONS_KEY)
        )

        # build layouts
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.table)
        save_and_load_bar = QHBoxLayout()
        save_button = QPushButton('Save Translations')
        # noinspection PyUnresolvedReferences
        save_button.clicked.connect(self.save_translations)
        save_and_load_bar.addWidget(save_button)
        load_button = QPushButton('Load Translations')
        # noinspection PyUnresolvedReferences
        load_button.clicked.connect(self.load_saved_translations)
        save_and_load_bar.addWidget(load_button)
        main_layout.addItem(save_and_load_bar)
        confirm_bar = QHBoxLayout()
        confirm_bar.addWidget(BackButton(self.reject))
        confirm_bar.addWidget(OkButton(self.accept))
        main_layout.addItem(confirm_bar)
        self.setLayout(main_layout)
        self.setMinimumWidth(DEFAULT_WIDGET_W)

    class TranslationTable(QTableWidget):
        def __init__(
                self,
                source_sheet: Sheet,
                target_sheet: Sheet,
                presets: list=None  # previous column translation dicts
        ) -> None:
            super().__init__()
            self.source_sheet = source_sheet
            self.target_sheet = target_sheet
            self.col_assoc = Associations()
            assert presets is None or isinstance(presets, list), \
                'Expected presets to be a list or None. Got %s' % presets
            if presets is not None:
                assert all([isinstance(item, dict) for item in presets])
            print('getting column names')
            self.src_col_names = [
                col.name for col in source_sheet.columns
                if col.name is not None
            ]
            self.tgt_col_names = [
                col.name for col in target_sheet.columns
                if col.name is not None
            ]
            print('setting presets')
            self.presets = presets if presets else []
            self.option_widget_classes = [
                self.SourceColumnDropDown,
                self.WhiteSpaceCheckbox,
                self.DuplicateCheckbox
            ]
            print('drawing table')
            self.draw_table()

        class SourceColumnDropDown(QComboBox):
            name = 'Source Column'
            dict_name = SOURCE_COLUMN_NAME_KEY
            default_value = NONE_STRING

            def __init__(self, table, start_value=None):
                super().__init__()
                self.table = table
                self.setToolTip('Select column to use as source')
                self.addItems(table.src_col_names + [NONE_STRING])
                start_value = self.find_start_value(start_value)
                self.setCurrentText(start_value)
                # todo: add margins to text box?
                # It's rather close to the left side.

            def find_start_value(self, preset: str=None) -> str:
                """
                Finds start value for SourceColumnDropDown.
                First checks to see if passed preset value is valid,
                if not, uses default.
                :param preset: str or None
                :return: str
                """
                if preset is not None and \
                        preset in self.table.source_sheet.columns.names or \
                        preset == self.default_value:
                    return preset
                else:
                    if self.currentText():
                        return self.currentText()
                    else:
                        return self.default_value

            @property
            def value(self):
                return self.currentText()

        class WhiteSpaceCheckbox(QCheckBox):
            name = 'Check for Whitespace'
            dict_name = WHITESPACE_CHK_KEY
            default_value = True

            def __init__(self, table, start_value=None):
                super().__init__()
                self.table = table
                self.setToolTip('Set whether whitespace is checked for in '
                                'this column')
                if start_value is None:
                    start_value = self.default_value
                self.setChecked(start_value)  # set start value

            @property
            def value(self):
                return self.isChecked()

        class DuplicateCheckbox(QCheckBox):
            name = 'Check for Duplicates'
            dict_name = DUPLICATE_CHK_KEY
            default_value = False

            def __init__(self, table, start_value=None):
                self.table = table
                super().__init__()
                self.setToolTip('Set whether duplicate values are checked for '
                                'in this column')
                if start_value is None:
                    start_value = self.default_value
                self.setChecked(start_value)  # set start value

            @property
            def value(self):
                return self.isChecked()

        def draw_table(self):
            """Draws table, populates columns, sets visual settings"""
            self.setRowCount(len(self.tgt_col_names))
            # set columns to number of options for each column
            self.setColumnCount(len(self.option_widget_classes))
            self.setAlternatingRowColors(True)
            # set row titles
            [self.setVerticalHeaderItem(y, QTableWidgetItem(column)) for
             y, column in enumerate(self.tgt_col_names)]
            # set option column titles
            [self.setHorizontalHeaderItem(x, QTableWidgetItem(option.name))
             for x, option in enumerate(self.option_widget_classes)]
            self.populate_table(self.presets)
            self.auto_fill()  # attempt to fill in cells left empty by presets

        def populate_table(self, translation_dict_list=None):
            assert len(self.tgt_col_names) > 0
            for y, target_column_name in enumerate(self.tgt_col_names):
                translation_dict = self.find_column_translation_dict(
                    target_column_name=target_column_name,
                    translation_dict_list=translation_dict_list
                )
                for x, option_class in enumerate(self.option_widget_classes):
                    self.setCellWidget(y, x, option_class(
                        table=self,
                        start_value=translation_dict.get(
                            option_class.dict_name, None
                        )
                    ))
            self.resizeColumnsToContents()

        def auto_fill(self) -> None:
            """
            Attempts to fill all unfilled source column fields using
            previously entered values for the same target column name.
            As currently written, this method assumes that the target
            column name resides at index 0 of
            :return: None
            """
            if self.col_assoc.is_empty():
                return
            y = 0
            x = self.get_option_index(self.SourceColumnDropDown)
            filled_tgt_columns = []
            while True:  # iterate over rows in table
                tgt_row_name_item = self.horizontalHeaderItem(y)
                # this returns None if invalid index is passed.
                if tgt_row_name_item is None:
                    break
                assert isinstance(tgt_row_name_item, QTableWidgetItem), \
                    "Got: %s" % tgt_row_name_item
                tgt_row_name = tgt_row_name_item.text()
                drop_down_menu = self.cellWidget(y, x)
                assert isinstance(
                    drop_down_menu, self.SourceColumnDropDown), \
                    "got: %s" % drop_down_menu
                assert isinstance(drop_down_menu.value, str), "got: %s" % \
                    drop_down_menu.value
                if drop_down_menu.value != NONE_STRING:
                    for src_col_name in self.col_assoc[tgt_row_name]:
                        if src_col_name in self.src_col_names:
                            drop_down_menu.setCurrentText(src_col_name)
                            filled_tgt_columns.append(tgt_row_name)
                y += 1
            if filled_tgt_columns:
                msg = QMessageBox()
                msg.setDetailedText(
                    "The following target columns have been autofilled:\n%s"
                    % '\n'.join(filled_tgt_columns)
                )
                msg.setWindowTitle("Auto-Filled Columns")
                msg.setModal(True)
                msg.setText(
                    "One or more columns have been automatically filled"
                    "based on previous selections.\n"
                    "Please ensure all auto-filled columns are correct."
                )
                msg.exec()

        def store_col_associations(self) -> bool:
            """
            Stores associations made in table into associations obj and
            saves them.
            :return: bool
            """
            [self.col_assoc.add_assoc(
                translation_dict[TARGET_COLUMN_NAME_KEY],
                translation_dict[SOURCE_COLUMN_NAME_KEY]
            ) for translation_dict in self.settings]
            return self.col_assoc.save()  # return bool returned by save()
            # indicating whether save was successful.

        def find_column_translation_dict(
            self,
            target_column_name: int or float or str,
            translation_dict_list: list=None,
        ) -> dict:
            """
            Finds translation dict for passed column name
            :param target_column_name: int, float, or str
            :param translation_dict_list: list[dict]
            :return: dict
            """
            assert isinstance(target_column_name, (int, float, str))
            assert isinstance(translation_dict_list, list) or \
                translation_dict_list is None
            if translation_dict_list is None:
                translation_dict_list = self.presets
            assert isinstance(translation_dict_list, list)
            for translation_dict in translation_dict_list:
                assert isinstance(translation_dict, dict)
                if translation_dict[TARGET_COLUMN_NAME_KEY] == \
                        target_column_name:
                    return translation_dict
            else:
                return dict()

        def get_option_index(self, option) -> int:
            for i, option_class in enumerate(self.option_widget_classes):
                if option is option_class:
                    return i

        @property
        def settings(self):
            """
            Returns list of column translation settings dicts.
            Returned dictionary is a list of dictionaries.
            Interior dictionaries have setting name as key.
            At time of this writing, interior dict looks like:
            {
                TARGET_COLUMN_KEY: < col name >
                SOURCE_COLUMN_KEY: < col name >
                WHITESPACE_CHECK_KEY: < bool >
                DUPLICATE_CHECK_KEY: < bool >
            }
            :return: list
            """

            def combine_dicts(*dicts):
                d = {}
                [d.update(dict__) for dict__ in dicts]
                return d

            translation_dicts = [
                # return a list of dictionaries with widget key and value
                combine_dicts(
                    {
                        self.cellWidget(y, x).dict_name:
                            self.cellWidget(y, x).value
                        for x in range(len(self.option_widget_classes))
                    },
                    {
                        # since the tgt col is not in option_widget_classes,
                        # it needs to be added here.
                        TARGET_COLUMN_NAME_KEY: tgt_col_name
                    }
                )
                for y, tgt_col_name in enumerate(self.tgt_col_names)
            ]
            return translation_dicts

    def save_translations(self) -> None:
        """
        raises save dialog to save current translations to a file
        :return: None
        """
        translations = self.table.settings
        save_dir = OS.get_translations_save_dir_path()
        save_dlg = SaveTranslationsDlg(
            parent=self,
            saves_dir=save_dir
        )
        result = save_dlg.exec()
        if not result:
            return
        # write file
        save_file_path = os.path.join(
            save_dir,
            save_dlg.file_name_entry_field.text()) + \
            SERIALIZED_OBJ_SUFFIX
        try:
            with open(save_file_path, 'wb') as save_file:
                pickle.dump(translations, save_file)
            print('save accepted')
        except IOError:
            print('saving %s to file: %s failed.'
                  % (self.obj_to_save, save_file_path))
            print(sys.exc_info())

    def load_saved_translations(self) -> None:
        """
        raises load dialog to load translations from a file
        Gets loaded list from dialog and applies it to table.
        :return: None
        """
        print('loading saved translations')
        saves_dir = OS.get_translations_save_dir_path()
        load_dlg = LoadTranslationsDlg(
            parent=self,
            saves_dir=saves_dir
        )
        result = load_dlg.exec()
        if not result:  # if user has not accepted
            return
        # otherwise, get saved translations dict list
        translations_dicts = load_dlg.load()  # returns list of dicts
        if translations_dicts:  # if list is not empty
            self.table.populate_table(translations_dicts)

    def finish(self):
        self.table.store_col_associations()

    @property
    def settings(self):
        """
        Returns settings dictionary
        :return: dict
        """
        return {COLUMN_TRANSLATIONS_KEY: self.table.settings}


class PreliminarySettings(PyLeadDlg):
    class SettingField(QComboBox):
        def __init__(self):
            super().__init__()

    class SheetField(SettingField, QComboBox):
        # string appearing next to field in settings table
        side_string = ''  # replaced by child classes
        # name under which to store field str
        dict_string = ''  # replaced by child classes
        # values to default to, in order of priority
        default_strings = tuple()  # replaced by child classes

        def __init__(self, start_str='', default_values=None):
            assert isinstance(start_str, str), \
                'Expected start_str to be str, instead %s was passed %s.' \
                % (self.__class__.__name__, start_str)
            assert default_values is None or \
                isinstance(default_values, (tuple, list)), \
                '%s __init__ was passed %s for default_values. ' \
                'That should not be' % (self.__name__, default_values)
            super().__init__()
            self.start_str = start_str
            # add default values -before- standard defaults (order matters)
            if default_values:
                self.default_strings = tuple(default_values) + \
                                       tuple(self.default_strings)
            # set text to default value
            self.set_options()
            self.setCurrentText(str(self._find_default_value()))
            self.gui_setup()

        def gui_setup(self):
            pass  # does nothing here, inherited by child classes

        def check_valid(self):
            pass  # inherited

        def _find_default_value(self):
            # find default value
            if self.start_str:  # if a starting string has been passed,
                # use that.
                return self.start_str
            else:  # otherwise, find the first default value that works
                # for each sheet of both passed and native defaults,
                # check if they exist, if so, use that value
                existing_sheet = model.sheet_exists(*self.default_strings)
                if existing_sheet:
                    return existing_sheet
                else:
                    return ''

        def set_options(self):
            assert isinstance(model, Model)
            sheets = model.sheet_names
            assert all(isinstance(sheet, str) for sheet in sheets)
            self.addItems(sheet for sheet in model.sheet_names)

        @property
        def value(self):
            return self.currentText()

    class ImportSheetField(SheetField):
        """Gets name of sheet to import from"""
        dict_string = SOURCE_SHEET_KEY
        side_string = 'Import sheet name'
        default_strings = 'import', 'Sheet1', 'sheet1'

        def gui_setup(self):
            self.setToolTip('Sheet to import columns from')
            # self.setPlaceholderText('Import Sheet')

        def check_valid(self):
            sheet_name = self.currentText()  # get text entered by user
            assert isinstance(sheet_name, str)
            if model.sheet_exists(sheet_name):
                return True
            elif sheet_name == '':
                InfoMessage(
                    parent=self,
                    title='Field Left Blank',
                    main='Import sheet name left blank',
                    secondary='The name of the sheet to copy column data from '
                              'must be entered.'
                )
            else:
                InfoMessage(
                    parent=self,
                    title='Non-Existent Sheet',
                    main='Sheet does not exist',
                    secondary='Source sheet \'%s\' could not be found' %
                              sheet_name
                )

    class ExportSheetField(SheetField):
        """Gets name of sheet to export to"""
        dict_string = TARGET_SHEET_KEY
        side_string = 'Export sheet name'
        default_strings = 'export', 'Sheet2', 'sheet2'

        def gui_setup(self):
            self.setToolTip('Sheet to export columns to')
            # self.setPlaceholderText('Export Sheet')

        def check_valid(self):
            sheet_name = self.currentText()  # get text entered by user
            assert isinstance(sheet_name, str)
            if model.sheet_exists(sheet_name):
                return True
            elif sheet_name == '':
                InfoMessage(
                    parent=self,
                    title='Field Left Blank',
                    main='Export sheet name left blank',
                    secondary='The name of the sheet to copy column data to '
                              'must be entered.'
                )
            else:
                InfoMessage(
                    parent=self,
                    title='Non-Existent Sheet',
                    main='Sheet does not exist',
                    secondary='Target sheet \'%s\' could not be found' %
                              sheet_name
                )

    class StartLineField(QLineEdit, SettingField):
        # values to default to, in order of priority
        default_strings = '1',
        # string appearing next to field in settings table
        side_string = ''  # replaced by child classes
        # name under which to store field str
        dict_string = ''  # replaced by child classes

        def __init__(self, start_str='', default_values=None):
            assert isinstance(start_str, str), \
                'Expected start_str to be str, instead %s was passed %s.' \
                % (self.__class__.__name__, start_str)
            assert default_values is None or \
                isinstance(default_values, (tuple, list)), \
                '%s __init__ was passed %s for default_values. ' \
                'That should not be' % (self.__name__, default_values)
            super().__init__()
            self.start_str = start_str
            # add default values -before- standard defaults (order matters)
            if default_values:
                self.default_strings = tuple(default_values) + \
                                       tuple(self.default_strings)
            # set text to default value
            self.setText(str(self._find_default_value()))
            self.gui_setup()

        def gui_setup(self):
            pass  # does nothing here, inherited by child classes

        def _find_default_value(self):
            return self.default_strings[0]  # until a better method is
            # available

        def check_valid(self):
            if self.text() == '':
                self._invalid_row('%s cannot be blank.' % self.side_string)
            elif not self.text().isdigit():
                self._invalid_row('Value entered for %s ( %s ) does '
                                  'not appear to be an integer.' %
                                  (self.side_string, self.text()))
            elif self.value < 0:
                self._invalid_row('%s cannot be negative. Got: %s.' %
                                  (self.side_string, self.value))
            else:
                return True

        def _invalid_row(self, explain_str):
            InfoMessage(
                parent=self,
                title='Invalid Row Index',
                main='Entered row is invalid.',
                secondary=explain_str
            )

        @property
        def value(self):
            """
            Gets user entered value
            :return: int
            """
            return int(self.text())

    class ImportSheetStartLine(StartLineField):
        """Gets index of line to start importing from"""
        dict_string = SOURCE_START_KEY
        side_string = 'Import sheet start line'

        def gui_setup(self):
            self.setToolTip('Index of first row to be imported')
            self.setPlaceholderText('Import start row')

    class ExportSheetStartLine(StartLineField):
        """Gets index of line to start writing to"""
        dict_string = TARGET_START_KEY
        side_string = 'Export sheet start line'

        def gui_setup(self):
            self.setToolTip('Index of first row to be written to on target '
                            'sheet')
            self.setPlaceholderText('Export start row')

    class CancelButton(QPushButton):
        """Cancels out of macro"""

        def __init__(self, cancel_func):
            super().__init__()
            self.setText('Cancel')
            # noinspection PyUnresolvedReferences
            self.clicked.connect(cancel_func)  # not error
            self.show()

    def __init__(self, starting_dictionary=None):
        print('Preliminary Dlg began')
        super().__init__(starting_dictionary)
        # values of fields, may be passed in if user has previously
        # entered settings, or is perhaps loading existing settings
        values = starting_dictionary if starting_dictionary else {}

        # define fields to be in preliminary settings widget
        field_classes = (
            self.ImportSheetField,
            self.ExportSheetField,
            self.ImportSheetStartLine,
            self.ExportSheetStartLine
        )  # one of each of these will be instantiated in the grid

        # create grid
        grid = ExpandingGridLayout()
        self.setLayout(grid)

        # create fields; add one instance of each field class
        self.fields = []
        print('began field creation')
        for x, field_class in enumerate(field_classes):
            dict_str = field_class.dict_string
            start_str = ''
            additional_default_values = [values[dict_str]] if \
                dict_str in values else []

            # create and add the field
            field = field_class(start_str=start_str,
                                default_values=additional_default_values)
            assert isinstance(field, self.SettingField)
            self.fields.append(field)
            grid.add_row(field.side_string, field)
        # add ok and cancel buttons

        grid.add_row(self.CancelButton(self.reject),
                     OkButton(self._ok))
        # todo: limit / freeze size of window
        self.setWindowTitle(APP_WINDOW_TITLE)

    def _ok(self):
        """
        Method called when user clicks 'ok' button on Preliminary
        Settings Widget.
        Creates AssociationTableWidget and passes it the created
        settings dictionary.
        """
        # check that entered sheets exist
        if any([not field.check_valid() for field in self.fields]):
            # field.check_valid displays info dialogs to user
            # if not valid.
            return  # does not move on if any fields are not valid
        # check that source and target sheets have detectable 
        # column headers
        if not self.check_sheets_are_not_identical():
            return
        if not self.check_sheets_have_column_headers():
            return
        self.accept()

    def check_sheets_are_not_identical(self):
        """
        Checks that source and target are different sheets
        :return: bool
        """
        if self.settings[SOURCE_SHEET_KEY] == self.settings[TARGET_SHEET_KEY]:
            InfoMessage(
                parent=self,
                title="Identical Sheets",
                main='Source and target sheets appear to be the same',
                secondary='Source and target sheets appear to both be set to'
                          ' %s' % self.settings[SOURCE_SHEET_KEY]
            )
            return False
        return True

    def check_sheets_have_column_headers(self) -> bool:
        """
        Checks that source and target sheets have column headers at
        passed row indices.
        :return: bool 
        """
        src_sheet_name = self.settings[SOURCE_SHEET_KEY]
        src_header_i = self.settings[SOURCE_START_KEY] - 1
        tgt_sheet_name = self.settings[TARGET_SHEET_KEY]
        tgt_header_i = self.settings[TARGET_START_KEY] - 1
        return all([
            self.check_sheet_has_headers(src_sheet_name, src_header_i),
            self.check_sheet_has_headers(tgt_sheet_name, tgt_header_i)
        ])  # return bool whether or not all sheets have column headers

    def check_sheet_has_headers(
            self,
            sheet_name: str,
            header_index: int
    ) -> bool:
        """
        Checks that passed 
        :param sheet_name: str
        :param header_index: 
        :return: 
        """
        assert isinstance(sheet_name, str)
        assert isinstance(header_index, int)
        sheet = model[sheet_name]
        assert isinstance(sheet, Sheet)
        sheet.reference_row_index = header_index
        if len([
            col.name for col in sheet.columns
            if col.name is not None
        ]) == 0:
            InfoMessage(
                parent=self,
                title="No Columns Found",
                main='No Columns found in sheet',
                secondary='Sheet %s has no columns that have headers at row '
                          'index %s (0-based).' % (repr(sheet_name),
                                                   header_index))
            return False
        return True

    @property
    def settings(self):
        """
        Gets dictionary of values stored in each field
        :return: dict
        """
        return {field.dict_string: field.value for field in self.fields}


class LogDlg(PyLeadDlg):
    """
    Dialog in which user inputs settings for what logs to check against
    for duplicates, what group to add logs to, and in which the user
    can add or remove log files
    """

    def __init__(self, settings: dict) -> None:
        super().__init__(settings)
        self.row_log = RowLog(OS.get_log_dir_path())
        # create group selector
        self.group_selector = QComboBox()
        self.group_selector.addItems(self.row_log.group_names)
        self.group_selector.setToolTip('Select log group to check')
        self.group_selector.setCurrentText(settings.get(LOG_GROUP_KEY, ''))
        # create checkbox for selecting whether or not log is checked
        # for duplicates.
        self.read_log_checkbox = QCheckBox()
        self.read_log_checkbox.setChecked(settings.get(LOG_READ_KEY, False))
        self.read_log_checkbox.setText('check for duplicates')
        self.read_log_checkbox.setToolTip(
            'Look for duplicates in log of previously moved values')
        # set whether log_group_selector is greyed depending on
        # checkbox val.
        # noinspection PyUnresolvedReferences
        self.read_log_checkbox.stateChanged.connect(self.log_checkbox_event)
        # create checkbox for selecting whether or not log should be
        # written to.
        self.write_log_checkbox = QCheckBox()
        self.write_log_checkbox.setChecked(settings.get(LOG_WRITE_KEY, False))
        self.write_log_checkbox.setText('write to log')
        self.write_log_checkbox.setToolTip(
            'Write moved values into a log to be checked later for duplicates'
        )
        # noinspection PyUnresolvedReferences
        self.write_log_checkbox.stateChanged.connect(self.log_checkbox_event)
        self.log_checkbox_event()  # set group selector + list enabled/disabled
        # create list of log files which displays currently selected
        # files in group.
        self.log_file_list = self.LogFileList(self.row_log)
        # button for adding a new group to row log
        self.add_group_btn = QPushButton()
        self.add_group_btn.setText('Add Group')
        self.add_group_btn.setToolTip('Add new group of log files')
        # noinspection PyUnresolvedReferences
        self.add_group_btn.clicked.connect(self.add_group)
        # button for removing a group from row log
        self.delete_group_btn = QPushButton()
        self.delete_group_btn.setText('Delete Group')
        self.delete_group_btn.setToolTip('Delete group of log files')
        # noinspection PyUnresolvedReferences
        self.delete_group_btn.clicked.connect(self.delete_group)
        self.back_button = BackButton(self.reject)
        self.accept_button = QPushButton()
        self.accept_button.setText('Next')
        self.accept_button.setToolTip('Go to next dialog')
        # noinspection PyUnresolvedReferences
        self.accept_button.clicked.connect(self.accept)
        # create line with accept / back buttons.
        button_line = QHBoxLayout()
        button_line.addWidget(self.back_button)
        button_line.addWidget(self.accept_button)
        layout = QVBoxLayout()
        layout.addWidget(self.read_log_checkbox)
        layout.addWidget(self.write_log_checkbox)
        layout.addWidget(self.group_selector)
        layout.addWidget(self.log_file_list)
        self.setLayout(layout)

    def log_checkbox_event(self):
        """
        method called on change to write_log or read_log checkboxes.
        :return: None
        """
        enabled = self.write_log_checkbox.isChecked() and \
            self.read_log_checkbox.isChecked()
        self.group_selector.setEnabled(enabled)
        self.log_file_list.setEnabled(enabled)

    class LogFileList(QListWidget):
        def __init__(self, row_log: 'RowLog') -> None:
            super().__init__()
            self.row_log = row_log
            self._group_name = None

        @property
        def group_name(self) -> str:
            return self._group_name

        @group_name.setter
        def group_name(self, group_name: str) -> None:
            if group_name != self._group_name:
                self._group_name = group_name
                self.clear()
                self.addItems([f for f in self.row_log.file_names(group_name)])

    def add_group(self):
        """
        Method called when user clicks new group button
        :return: None
        """
        # get name of group from user
        # noinspection PyTypeChecker,PyCallByClass,PyArgumentList
        name, ok = QInputDialog.getText(
            self,  # parent
            'New Log Group',  # Title
            'Enter name of new log group'  # content prompt
        )
        # create group
        if not ok:
            return
        try:
            self.row_log.new_group(name)
        except OSError:
            # if group cannot be created, display message
            failure_dlg = QMessageBox()
            failure_dlg.setIcon(QMessageBox.Warning)
            failure_dlg.setWindowTitle('Failed to Create Group')
            failure_dlg.setText(
                'Could not create group %s because a directory of that '
                'name could not be created. Check permissions for the'
                '%s directory' % (name, self.row_log.path)
            )

    def delete_group(self):
        """
        Remove group and files contained.
        :return: None
        """
        # have user select group to be removed
        # noinspection PyTypeChecker,PyCallByClass,PyArgumentList
        name, ok = QInputDialog.getItem(
            self,  # parent
            'Delete Log Group',  # title
            'Select group to be deleted',  # text
            [f for f in self.row_log.group_names],  # selectable items
            0,  # starting index
        )
        # delete group
        if not ok:
            return
        # get confirmation
        confirm_dlg = QMessageBox()
        confirm_dlg.setWindowTitle('Confirm Deletion')
        confirm_dlg.setText(
            'Are you sure you wish to delete log group %s' % repr(name)
        )
        confirm_dlg.setStandardButtons(
            QMessageBox.Cancel |
            QMessageBox.Yes
        )
        confirmed = confirm_dlg.exec()
        if not confirmed:
            return
        try:
            self.row_log.delete_group(name)
        except OSError:
            # if group cannot be created, display message
            failure_dlg = QMessageBox()
            failure_dlg.setIcon(QMessageBox.Warning)
            failure_dlg.setWindowTitle('Failed to Delete Group')
            failure_dlg.setText(
                'Could not delete group %s because the directory %s or a file'
                'within it could not be deleted'
                % (repr(name), repr(os.path.join(self.row_log.path, name)))
            )

    @property
    def settings(self) -> dict:
        """
        Gets settings dict
        :return: dict
        """
        return {
            LOG_WRITE_KEY: self.write_log_checkbox.isChecked(),
            LOG_READ_KEY: self.read_log_checkbox.isChecked(),
            LOG_GROUP_KEY: self.group_selector.currentText(),
        }


class FinalSettings(PyLeadDlg):
    def __init__(self, settings: dict):
        assert isinstance(settings, dict), \
            'expected dict or Settings, got instead: %s' % settings
        print('Final Settings dlg began')
        super().__init__(settings)

        field_classes = [
            self.DuplicateActionOption,
            self.WhitespaceOption,
        ]

        def back():
            self.reject()

        layout = ExpandingGridLayout()
        self.fields = []  # list of fields for user to input/select strings
        for field_class in field_classes:
            start_val = settings.get(field_class.dict_str)
            field = field_class(start_value=start_val)
            layout.add_row(field_class.side_string, field)
            self.fields.append(field)
        layout.add_row(BackButton(back), self.ApplyButton(self))
        self.setLayout(layout)
        self.setWindowTitle(APP_WINDOW_TITLE)

    class ApplyButton(QPushButton):
        def __init__(self, host):
            assert isinstance(host, FinalSettings)
            super().__init__()
            self.host = host

            def apply():
                self.host.accept()

            # noinspection PyUnresolvedReferences
            self.clicked.connect(apply)  # not an error
            self.setText('Apply')
            self.setToolTip('Apply selections & move cells from source sheet '
                            'to target')

    class MenuOption(QComboBox):
        options = tuple()  # overridden by child classes
        default_option = ''
        tool_tip = ''
        dict_str = ''
        side_string = ''

        def __init__(self, start_value=None):
            super().__init__()
            self.addItems(self.options)
            self.setToolTip(self.tool_tip)
            self.setCurrentText(start_value if start_value else
                                self.default_option)
            # todo: add margins?

        @property
        def value(self):
            return self.currentText()

    class DuplicateActionOption(MenuOption):
        options = 'Do nothing', 'Highlight', 'Remove row'
        default_option = 'Highlight'
        tool_tip = 'Select action to be taken for rows containing ' \
                   'duplicate in checked columns'
        dict_str = DUPLICATE_ACTION_KEY
        side_string = 'Action for duplicates'

    class WhitespaceOption(MenuOption):
        options = 'Do nothing', 'Highlight', 'Remove Whitespace'
        default_option = 'Highlight'
        tool_tip = 'Select action to be taken for cells containing whitespace'
        dict_str = WHITESPACE_ACTION_KEY
        side_string = 'Action for whitespace'

    @property
    def settings(self):
        """
        Returns grand collection of all settings inputted by user
        :return: dict
        """
        return {option.dict_str: option.value for option in self.fields}

# SAVE / LOAD dlg


class FileDlg(QDialog):
    """
    Superclass for SaveDlg and LoadDlg.
    In this class, the save folder and its contents are found and
    prepared for use by subclass methods.
    """
    title = 'placeholder, replaced by subclasses'

    def __init__(self, parent: QWidget, saves_dir: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.title)
        self.setModal(True)
        self.setFocus()
        assert isinstance(saves_dir, str), 'expected str, got %s' % saves_dir
        self.saves_dir_path = saves_dir
        if not OS.ensure_dir_exists(saves_dir):
            print('%s could not find path %s and failed to create it.' %
                  (self.__class__.__name__, saves_dir))
            msg = QMessageBox(
                QMessageBox.Information,  # icon
                'Could not find saved files',  # title
                'Could not find or create saved translations directory %s'
                % saves_dir
            )
            msg.exec()
            self.close()

    def get_save_file_names(self) -> set:
        """
        Gets list of files in saves dir
        :return: set[str]
        """
        try:
            return set([
                os.path.splitext(file_name)[0] for file_name in
                os.listdir(OS.get_translations_save_dir_path())
            ])
        except IOError:
            print('could not get saved files in directory: %s'
                  % self.saves_dir_path)
            print(sys.exc_info())
            return set()


class SaveTranslationsDlg(FileDlg):
    """
    Dialog handling saving column translations dict to file
    """
    title = 'Save Column Settings'

    def __init__(
            self,
            parent: QWidget,
            saves_dir: str
    ) -> None:
        print('Save dialog initialization began')
        super().__init__(parent, saves_dir)
        grid = ExpandingGridLayout()
        self.file_name_entry_field = QLineEdit()
        self.file_name_entry_field.setToolTip(
            'Enter name to save translations as')
        self.accept_button = QPushButton('Save')
        # noinspection PyUnresolvedReferences
        self.accept_button.clicked.connect(self.save)  # not an error
        self.cancel_button = QPushButton('Cancel')
        # noinspection PyUnresolvedReferences
        self.cancel_button.clicked.connect(self.reject)  # not an error
        grid.add_row(self.file_name_entry_field)
        grid.add_row(self.accept_button, self.cancel_button)
        self.setLayout(grid)

    def save(self):
        """
        Saves translations to file
        :return: None
        """
        file_name = self.file_name_entry_field.text()
        # if file_name would overwrite an existing file,
        # get user confirmation
        if file_name in self.get_save_file_names() and \
                not self.confirm_overwrite(file_name):
            return
        self.accept()

    def confirm_overwrite(self, file_name):
        reply = QMessageBox.question(
            self,
            'Overwrite File?',
            'A file named %s already exists, overwrite it?' % file_name,
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel
        )
        return reply == QMessageBox.Yes


class LoadTranslationsDlg(FileDlg):
    """
    Dialog handling loading of column translations dict from file
    """
    title = 'Load Saved Movements'

    def __init__(self, parent: QWidget, saves_dir: str) -> None:
        print('Load Translations Dialog initialization began')
        super().__init__(parent, saves_dir)
        grid = ExpandingGridLayout()
        self.file_selection_field = QComboBox()
        self.populate_file_selection_field()
        self.file_selection_field.setToolTip('Select save to load')
        self.file_selection_field.setCurrentText('Select save')
        self.delete_button = QPushButton('Delete Save')
        self.cancel_button = QPushButton('Cancel')
        self.accept_button = QPushButton('Load')
        # noinspection PyUnresolvedReferences
        self.delete_button.clicked.connect(self.delete)
        # noinspection PyUnresolvedReferences
        self.cancel_button.clicked.connect(self.reject)
        # noinspection PyUnresolvedReferences
        self.accept_button.clicked.connect(self.accept)
        grid.add_row(self.file_selection_field, self.delete_button)
        grid.add_row(self.cancel_button, self.accept_button)
        self.setLayout(grid)

    def populate_file_selection_field(self):
        """
        Populates selection field with sorted file names
        :return: None
        """
        self.file_selection_field.clear()
        file_names = list(self.get_save_file_names())
        file_names.sort()
        self.file_selection_field.addItems(
            file_names
        )

    def delete(self) -> bool:
        """
        Deletes selected file. Returns bool of whether delete was successful.
        :return: bool
        """
        # first get confirmation
        # then delete file
        file_name = self.file_selection_field.currentText()
        if file_name == '':
            return False
        file_path = os.path.join(
            OS.get_translations_save_dir_path(),
            file_name) + SERIALIZED_OBJ_SUFFIX
        try:
            os.remove(file_path)
            self.populate_file_selection_field()  # update
            return True
        except IOError:
            print('could not delete file %s' % file_path)
            print(sys.exc_info())
            msg = QMessageBox(
                QMessageBox.Information,  # icon
                'Delete Failed',  # title
                'Could not delete file %s' % file_path,  # body
            )
            print('file path: %s' % file_path)
            print('file path type: %s' % file_path.__class__.__name__)
            print('file path str: %s' % str(file_path))
            print('file path repr: %s' % repr(file_path))
            msg.setDetailedText('\n'.join([str(i) for i in sys.exc_info()]))
            msg.exec()
            return False

    def load(self) -> list:
        """
        loads column translations from save file.
        returns list of column translation dicts
        :return: list[dict]
        """
        file_name = self.file_selection_field.currentText()
        file_path = os.path.join(
            OS.get_translations_save_dir_path(), file_name) + \
            SERIALIZED_OBJ_SUFFIX
        try:
            with open(file_path, 'rb') as file:
                translations_list = pickle.load(file)
            if not isinstance(translations_list, list) or \
                    not all([isinstance(i, dict) for i in translations_list]):
                raise TypeError('expected list of dicts, got %s'
                                % translations_list)
            return translations_list
        except IOError:
            print('Could not load from file path: %s' % file_path)
            print(sys.exc_info())
            msg = QMessageBox(
                QMessageBox.Information,  # icon
                'Loading Failed',  # title
                'Could not load column translations from file',  # msg
            )
            msg.setDetailedText('\n'.join([str(i) for i in sys.exc_info()]))
            msg.exec()
            return []


class InfoMessage(QMessageBox):
    """
    Displays simple information dialogue with title, main message,
    and secondary message beneath that.
    Icon is an Info 'I.'
    """

    def __init__(self, parent, title, main, secondary='', detail=''):
        for item in (title, main, secondary, detail):
            assert isinstance(item, str), \
                'expected str, got: %s, (%s)' % (item, item.__class__.__name__)
        super().__init__(parent)
        self.setIcon(QMessageBox.Information)
        self.setWindowTitle(title)
        self.setText(main)
        if secondary:
            self.setInformativeText(secondary)
        self.setStandardButtons(QMessageBox.Ok)
        if detail is not '':
            self.setDetailedText(detail)
        self.exec()


class ConfirmDialog(QMessageBox):
    """
    Dialog for user to accept or cancel
    """

    def __init__(self, parent, title, main, secondary=''):
        assert all([isinstance(item, str)for item in (title, main, secondary)])
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setText(main)
        if secondary:
            self.setInformativeText(secondary)
        self.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        self.setDefaultButton(QMessageBox.Ok)


class OkButton(QPushButton):
    """ calls passed function when clicked by user."""

    def __init__(self, ok_function):
        super().__init__('OK')
        # noinspection PyUnresolvedReferences
        self.clicked.connect(ok_function)  # not error
        self.setToolTip('Move to next page')
        self.show()


class BackButton(QPushButton):
    def __init__(self, back_function):
        super().__init__('Back')
        self.setToolTip('Go to last page')
        # noinspection PyUnresolvedReferences
        self.clicked.connect(back_function)  # not error
        self.show()


class ExpandingGridLayout(QGridLayout):
    """
    Grid layout that can be simply expanded
    """

    def __init__(self):
        super().__init__()

    def add_row(self, *items):
        """
        Adds a row to the grid, consisting of the passed items
        :param items: items
        """
        y = self.rowCount()
        for x, item in enumerate(items):
            # convert string to label
            if isinstance(item, str):
                item = QLabel(item)
            self.addWidget(item, y, x)


###############################################################################
# SETTINGS / DATA


class OS:
    """
    Handles interaction with different operating systems.

    This may not need to be a class, but any independent functions appear
    as their own macro, so this is instead its own class
    """
    if platform.system() not in ('Linux', 'Windows', 'Mac'):
        raise OSError('Operating System \'%s\' not supported. Supported'
                      'operating systems are Linux, Windows, and Mac')

    @staticmethod
    def get_app_data_path():
        # get method name that should return path
        data_path_func_name = '_get_%s_data_path' % platform.system().lower()
        if hasattr(OS, data_path_func_name):
            data_path_func = getattr(OS, data_path_func_name)
        else:
            raise AttributeError('Could not find %s function in OS class'
                                 % data_path_func_name)
        return data_path_func()

    @staticmethod
    def _get_linux_data_path():
        """
        Gets data folder path for macro on Linux system.
        :return: str path
        """
        home_folder_path = os.getenv('HOME')
        return os.path.join(home_folder_path, '.config', APP_FOLDER_NAME)

    @staticmethod
    def _get_windows_data_path():
        """
        Gets data folder path for macro on Windows system.
        :return: str path
        """
        app_folder_path = os.getenv('APPDATA')
        return os.path.join(app_folder_path, APP_FOLDER_NAME)

    @staticmethod
    def _get_mac_data_path() -> str:
        """
        Gets data folder path for macro on Mac system.
        :return: str path
        """
        raise NotImplementedError('have not yet set up mac path')

    @staticmethod
    def get_translations_save_dir_path() -> str:
        """
        Gets path to folder where translations are saved.
        :return: str
        """
        return os.path.join(
            OS.get_app_data_path(),
            SAVED_TRANSLATIONS_FOLDER_NAME
        )

    @staticmethod
    def get_log_dir_path() -> str:
        """
        Gets path to dir where logs are stored.
        :return: str
        """
        return os.path.join(
            OS.get_app_data_path(),
            LOG_DIR_NAME
        )

    @staticmethod
    def ensure_dir_exists(file_path: str) -> bool:
        """
        Checks that file path exists, creates it if it does not,
        and returns bool of whether file path now exists (
        returning false if an error arose)
        :param file_path: str
        :return: bool
        """
        if not os.path.exists(file_path):
            print('path %s does not exist, creating it' % file_path)
            # get higher level path, check if that exists
            higher_dir = os.path.join(*os.path.split(file_path)[:-1])
            if not os.path.exists(higher_dir):
                OS.ensure_dir_exists(higher_dir)
            try:
                os.mkdir(file_path)
            except OSError as e:
                print(sys.exc_info())
                print(e.strerror)
                return False
        return True


class Settings(dict):
    settings_file_name = 'settings'

    def __init__(self, macro_folder):
        super().__init__()
        print('created settings')
        self.file_path = os.path.join(
            macro_folder,
            self.settings_file_name + SERIALIZED_OBJ_SUFFIX
        )
        self.load()

    def save(self):
        """
        Saves settings in settings file.
        :return: bool of whether saving was successful
        """
        try:
            self.saved_settings = self.dict
        except IOError:
            return False
        else:
            return True

    def load(self):
        """
        Loads settings from settings file in file path
        :return bool of whether loading was successful
        """
        try:
            self.clear()
            self.update(self.saved_settings)
        except IOError:
            self.clear()
            return False
        else:
            return True

    def check_settings_dir_exists(self) -> bool:
        """
        Ensure that dir containing settings exists
        :return: bool of whether dir exists
        (either pre-existing or was created)
        """
        settings_dir = os.path.dirname(self.file_path)
        print('checking settings dir \'%s\' exists' % settings_dir)
        return OS.ensure_dir_exists(settings_dir)

    @property
    def saved_settings(self) -> dict:
        """
        Gets settings dictionary if one exists, otherwise returns
        an empty dictionary.
        Will raise IOError if this could not be accomplished.
        :return: dict
        """
        print('loading settings from %s' % self.file_path)
        self.check_settings_dir_exists()
        try:
            with open(self.file_path, 'rb') as settings_file:
                settings = pickle.load(settings_file)
        except IOError and FileNotFoundError:
            print('Could not load settings from file.')
            print(sys.exc_info())
            raise IOError('Could not load settings from existing file')
        except EOFError:
            print('No information in file')
            return {}
        else:
            print('got settings: %s' % settings)
            return settings

    @saved_settings.setter
    def saved_settings(self, new_settings: dict):
        """
        Stores settings dictionary.
        Will ask permission from user and try to create folder + file
        if needed.
        Will raise IOError if this could not be accomplished.
        :param new_settings: dict
        """
        print('saving settings to %s' % self.file_path)
        self.check_settings_dir_exists()
        try:
            with open(self.file_path, 'wb') as settings_file:
                pickle.dump(new_settings, settings_file)
        except IOError:
            print('could not save settings to file')
            print(sys.exc_info())
            raise IOError('could not save settings to file')
        else:
            print('Saved Settings:')
            print(new_settings)

    @property
    def dict(self) -> dict:
        """
        Gets plain dict of key/values in self,
        useful to allow stored data to be pickled more easily.
        :return: dict
        """
        return {key: self[key] for key in self.keys()}


class Associations:
    """
    Stores table of associations for each target column.
    For a given target column name, stores names of source
    columns from which data has been retrieved.
    This is intended to be used to auto-fill translation table
    entries.
    """
    _assoc_deque = collections.deque()
    association_table_file_name = 'associations'
    max_source_entries = 1000

    def __init__(self, file_path: str=None):
        if file_path is None:
            # if no file_path is passed, create default path.
            file_path = os.path.join(
                OS.get_app_data_path(),
                self.association_table_file_name + SERIALIZED_OBJ_SUFFIX
            )
        if not isinstance(file_path, str):
            raise TypeError('passed file_path must be a str. Got: %s'
                            % file_path)
        self._file_path = file_path
        self.load_file_path(self._file_path)
        self.unmapped_index = 0  # first unmapped assoc in deque
        # modified since last access
        self._assoc_dict = {}
        print("finished creating assoc obj")

    def __getitem__(self, key):
        """
        Gets values associated with a passed key
        :param key: object
        :return: object
        """
        # this method implementation delays mapping of values to the last
        # possible moment, only mapping values in the deque when
        # __getitem__ is called, and then only mapping as required to yield
        # values. If only the first yielded value is needed, no more
        # associations are mapped.
        # first yield each value that has been mapped
        for value in self._assoc_dict.get(key, []):  # default to an empty list
            yield value
        # then look for additional values if any remain
        while self.unmapped_index < len(self._assoc_deque):
            assoc = self._assoc_deque[self.unmapped_index]
            assert isinstance(assoc, tuple), "Got: %s" % repr(assoc)
            self._map_assoc(assoc)
            if assoc[0] == key:
                yield assoc[1]

    def load_file_path(self, file_path: str):
        """
        Loads associations from file.
        :param file_path: str path
        :return: None
        """
        if not isinstance(file_path, str):
            raise TypeError('file_path must be str. Got: %s' % file_path)
        assoc_deque = None
        try:
            with open(file_path, 'rb') as assoc_file:
                assoc_deque = pickle.load(assoc_file)
        except IOError:
            print('could not load assoc file.')
            print('\n'.join([str(i) for i in sys.exc_info()]))
        if assoc_deque is not None:
            assert isinstance(assoc_deque, collections.deque), \
                "got: %s" % assoc_deque
            if not all([isinstance(value, tuple) for value in
                        assoc_deque]):
                raise ValueError(
                    'Association dict values are not all lists. Got %s.')
            self._assoc_deque = assoc_deque
            self.unmapped_index = 0  # reset counter

    def save(self, file_path: str=None) -> bool:
        """
        Saves associations to a file.
        Returns bool of whether save was successful.
        :param file_path: file path to save to. If not passed, uses default
        :return: bool
        """
        self.clean()  # clean extra associations before saving
        if file_path is None:
            file_path = self._file_path
        elif not isinstance(file_path, str):
            raise TypeError('file_path should be a str. Got: %s' % file_path)
        try:
            with open(file_path, 'wb') as assoc_file:
                pickle.dump(self._assoc_deque, assoc_file)
        except IOError:
            print('could not save associations to file')
            print('\n'.join([str(i) for i in sys.exc_info()]))
            return False
        else:
            return True

    def add_assoc(self, key: object, value: object):
        """
        Associates value with key.
        :param key: object
        :param value: object
        :return: None
        """
        new_assoc = key, value
        assert isinstance(new_assoc, tuple)
        self._assoc_deque.appendleft(new_assoc)
        self._map_assoc(new_assoc)

    def _map_assoc(self, association: tuple):
        """
        Adds association to dictionary of associations
        :param association: tuple
        """
        assert isinstance(association, tuple), "Got: %s" % repr(association)
        try:
            self._assoc_dict[association[0]].append(association[1])
        except KeyError:
            self._assoc_dict[association[0]] = [association[1]]
        self.unmapped_index += 1  # increment counter

    def clean(self, force: bool or int=False) -> int:
        """
        Cleans AssociationMap of old associations.
        Returns integer of number of associations removed.
        :param force: int of number of items to remove.
            if 0 or False, removes only enough to reach limit
            if 1 or True, removes only the oldest association.
        :return: int
        """
        n_removed = 0
        if force is True:
            force = 1
        elif force is False:
            force = 0
        if not force:
            target_n = self.max_source_entries  # number to reduce to
        else:
            target_n = len(self._assoc_deque) - force
        while len(self._assoc_deque) > target_n:
            del self._assoc_deque[-1]  # delete last entry
            n_removed += 1
        self.unmapped_index = 0  # reset counter
        return n_removed

    def values(self):
        """
        Returns iterator of associations made, regardless of key
        :return:
        """
        for entry in self._assoc_deque:
            return entry[1]

    def is_empty(self) -> bool:
        return len(self._assoc_deque) == 0


class RowLog:
    """
    Keeps a record of previously translated rows, to detect duplicates.

    These records are kept in a logs folder in the app dir, where
    each source translation is recorded as a new file
    """
    translation_logs_dir_name = 'logs'
    log_file_ext = '.csv'

    def __init__(self, path: str):
        OS.ensure_dir_exists(path)
        assert os.path.exists(path)
        self.path = path
        self._groups = self._find_groups()

    def file_names(self, group_name):
        """
        Gets file names in the group identified by passed group name.
        :param group_name: str
        :return: Generator[str]
        """
        for file_name in self._groups[group_name].file_names:
            yield file_name

    def _find_groups(self):
        """
        Looks through self.path for sub-directories,
        and adds them as groups.
        :return: dict
        """
        return {
            item_name: RowLog.Group(os.path.join(self.path, item_name)) for
            item_name in os.listdir(self.path) if
            os.path.isdir(os.path.join(self.path, item_name))
        }

    def find_duplicates(
            self,
            value: int or float or str,
            group: str,
            column_name: int or float or str
            ):
        """
        Finds duplicates of passed value in columns of passed name.
        Returns generator of tuple[log file name, row index]
        :param value: int, float or str
        :param group: str
        :param column_name: int, float, or str
        :return: Generator[tuple[log file name str, row index]]
        """
        return self._groups[group].find_duplicates(value, column_name)

    def new_group(self, name: str) -> None:
        """
        Creates a new group with passed name
        :param name: str
        :return: None
        """
        self._groups[name] = RowLog.Group(os.path.join(self.path, name))

    def delete_group(self, name: str) -> None:
        """
        Deletes group and contained files
        :param name: str
        :return: None
        """
        group = self._groups[name]
        [os.remove(os.path.join(group.path, f)) for f in group.file_names]
        os.rmdir(group.path)
        del self._groups[name]

    def make_log(self, group_name: str, sheet: 'Sheet'):
        """
        Creates a log file from a source sheet
        :param group_name: str name of group to add sheet to
        :param sheet: Sheet to log
        :return: None
        """
        self._groups[group_name].add_file(sheet)

    @property
    def group_names(self):
        """
        Yields each group name in self
        :return: Generator[str]
        """
        for group_name in self._groups:
            assert isinstance(group_name, str)
            yield group_name

    class Group:
        """
        Class representing a grouping of source leads
        """
        def __init__(self, path: str) -> None:
            if os.path.exists(path) and not os.path.isdir(path):
                raise ValueError('Path passed exists and is not a dir')
            self.path = path
            if not OS.ensure_dir_exists(path):  # ensure .path is a dir
                raise IOError('path %s does not exist and could not be'
                              'created.' % self.path)
            self.log_files = self._find_log_files()

        def _find_log_files(self) -> dict:
            """
            Returns dict of log files, with file name as key,
            RowLogFile as value.
            :return: dict[str:RowLogFile]
            """
            return {
                filename:
                    RowLog.RowLogFile(os.path.join(self.path, filename)) for
                filename in os.listdir(self.path) if
                filename.endswith(RowLog.log_file_ext)
            }

        def find_duplicates(
                self,
                value: int or float or str,
                column_name: int or float or str
                ):
            """
            Finds duplicates. Yields generator of
            tuple[file name str, row index int]
            :param value: int, float, or str
            :param column_name: int, float, or str
            :return: Generator[tuple[str, int]]
            """
            for log_file in self.log_files.values():
                for index in log_file.find_duplicates(value, column_name):
                    yield log_file.name, index

        def add_file(self, sheet: 'Sheet'):
            """
            Creates a RowLogFile in this group.
            :param sheet: Sheet
            :return: None
            """
            log = RowLog.RowLogFile(self.path, sheet)
            self.log_files[log.name] = log

        @property
        def name(self):
            if self.path.endswith('/'):
                path = self.path[:-1]
            else:
                path = self.path
            return os.path.basename(path)

        @property
        def file_names(self):
            """
            Gets generator of log files in this group
            :return: Generator[str]
            """
            for log_name in self.log_files:
                yield log_name

    class RowLogFile:
        """
        Class operating on a single log
        """
        prefix_dict = {
            int: 'int:',
            float: 'flt:',
            str: 'str:',
        }

        type_dict = {v: k for k, v in prefix_dict.items()}  # inverted prefix d

        none_str = 'None'

        def __init__(self, path: str, sheet: 'Sheet'=None) -> None:
            """
            Creates a new RowLogFile at/from passed path.
            If a sheet is passed to constructor,
            creates a new log at path. If no sheet is passed,
            attempts to read a log from file at path.
            When creating a new log file, if passed path str is a dir,
            new file is created within that dir. If path is not a dir,
            creates a file with that name.
            :param path: str
            :param sheet: sheet
            """
            if os.path.isdir(path):
                # if passed path is a dir, create a path for self within it
                assert sheet is not None  # sheet is needed for name generation
                self.path = os.path.join(path, self._generate_name())
            else:  # if passed path is a file/doesn't exist,
                # that will be used as the path for this log file.
                self.path = path
            self._rows = None  # list of rows read from this file.
            self._col_values = {}  # dictionary of column value sets
            if sheet:
                self.write(sheet)
            else:
                self.read(self.path)

        def write(self, sheet: 'Sheet'):
            """
            Writes sheet info to file.
            If path is a dir, writes to a file within that dir,
            otherwise, creates/writes to a file located at path.
            :param sheet: Sheet
            :return: None
            """
            with open(self.path, 'w') as f:
                writer = csv.DictWriter(
                    f, sheet.columns.names,  # generator
                    restval=None,
                    extrasaction='raise')  # raise ValueError on unexpected key
                writer.writerows([self._format_dict(row.to_dict()) for
                                  row in sheet.table_rows])

        def read(self, path: str=None) -> list:
            """
            Reads columns in from file.
            :param path: str path to file to red
            :return: list[dict]
            """
            path = path if path else self.path
            with open(path, 'r') as f:
                reader = csv.DictReader(f)
                # parse each row in reader from str to original types & return.
                return [self._parse_dict(row) for row in reader]

        def find_duplicates(
                self,
                value: int or float or str,
                column_name: int or float or str
                ):
            """
            Yields duplicates in this row file
            :param value: int, float, or str
            :param column_name: int, float or str
            :return: Generator[str, int]
            """
            try:
                for row_index in self.column_values(column_name)[value]:
                    yield row_index
            except KeyError:
                return

        @classmethod
        def _format_dict(cls, d: dict) -> dict:
            """
            Returns a new dictionary that is a formatted version of
            passed dict.
            :param d: dict
            :return: new dict
            """
            assert isinstance(d, dict)
            new_d = {}
            for k, v in d.items():
                new_d[k] = cls._format_val(v)
            return new_d

        @staticmethod
        def _format_val(v: int or float or str or None):
            """
            Formats value to be stored in csv file
            :param v: int, float, str, or None
            :return: str
            """
            if v is None:
                return RowLog.RowLogFile.none_str
            else:
                return RowLog.RowLogFile.prefix_dict[v.__class__] + str(v)

        @classmethod
        def _parse_dict(cls, d: dict) -> dict:
            """
            Parses dictionary and returns a new dictionary with
            those values.
            :param d: dict
            :return: new dict
            """
            assert isinstance(d, dict)
            new_d = {}
            for k, v in d.items():
                new_d[k] = cls._parse_val(v)
            return new_d

        @staticmethod
        def _parse_val(s: str) -> str or int or float or None:
            """
            Parses str for value stored by format_val method
            :param s:
            :return: str, int, float, or None
            """
            if not isinstance(s, str):
                raise ValueError('Expected str, got %s' % repr(s))
            prefix = s[:3]
            if prefix == RowLog.RowLogFile.none_str:
                return None
            else:
                # try to convert string value to value
                return RowLog.RowLogFile.type_dict[prefix](s)

        def column_values(self, col_name: int or float or str or None) -> dict:
            """
            Returns dict for a passed column name.
            :param col_name: int, float, str, or None
            :return: set
            """
            # col_values dict is lazily populated
            try:  # try to get {value: row indices} dict from col_values dict.
                d = self._col_values[col_name]
            except KeyError:  # if col_name key has not been entered, do that.
                d = self._col_values[col_name] = {}
                for row_i, row in enumerate(self.rows):  # for each row:
                    # get relevant value for col.
                    # this is accessed here to prevent a possible key error
                    # from silently breaking and being caught below.
                    v = row[col_name]
                    try:  # try to add row index to set of indices with value
                        d[v].add(row_i)
                    except KeyError:  # if key does not exist, create entry
                        d[v] = {row_i}
            return d

        @property
        def rows(self):
            """
            Gets rows from file.
            :return: list[dict]
            """
            if not self._rows:
                self._rows = self.read()  # read file at path
            return self._rows

        def _generate_name(self) -> str:
            return datetime.datetime.now().isoformat()

        @property
        def name(self) -> str:
            return os.path.basename(self.path)

        def __repr__(self) -> str:
            return 'RowLogFile[%s]' % self.path

        def display_name(self) -> str:
            """
            Gets user-friendly string to be used in gui.
            At this time, returns base name of log path without extension
            :return: str
            """
            return 'Log from: %s' % \
                   os.path.splitext(os.path.basename(self.path))[0]


class Color:
    """
    Handles color conversions such as hex -> RGB or RGB -> hex
    """
    color = 0

    def __init__(self, color):
        if isinstance(color, int):
            self.color = color  # store as int
        elif isinstance(color, tuple):
            if len(color) != 3:
                raise ValueError(
                    "Color: RGB tuple should be len 3. got: %s" % color
                )
            if any([(not isinstance(value, int) or value > 255)
                    for value in color]):
                raise ValueError(
                    "Color: each value in color rgb tuple should be an int"
                    "between 0 and 255. Got: %s" % color
                )
            r = color[0]
            g = color[1]
            b = color[2]
            self.color = (r << 16) + (g << 8) + b

        elif isinstance(color, str):
            raise ValueError("Color does not yet support string colors")
        elif isinstance(color, Color):
            self.color = color.color  # color has stopped sounding like a word
        else:
            raise TypeError("Color constructor was passed an "
                            "unknown color identifier: %s" % color)

    @property
    def rgb(self):
        r = (self.color >> 16) & 255
        g = (self.color >> 8) & 255
        b = self.color & 255
        return r, g, b


def lead_app():
    """
    Main lead sheet management macro.
    Calls each dialog in turn and then creates and applies Translation.
    """
    # flow:
    # preliminary settings ->
    # association table ->
    # final settings / info
    # push data to target
    # close / display exit message
    print('\nstarted pyleadsmacro')
    print('Python version %s.%s.%s %s. serial: %s' % sys.version_info)
    print('started app')

    # create model handler object and in doing so,
    # check interface is working correctly
    global model
    global app
    model = Office.get_model()
    app = QApplication([''])  # expects list of strings.

    # get settings
    settings = Settings(OS.get_app_data_path())
    # get settings from prelim dialog
    run = True
    step = 0

    dialog_classes = [
        PreliminarySettings,
        TranslationDialog,
        LogDlg,
        FinalSettings
    ]
    while run:
        dlg = dialog_classes[step](settings)  # create dlg for current step
        result = dlg.exec_()  # run dlg and get result.
        settings.update(dlg.settings)
        dlg.finish()
        if dlg.quit_flag:
            run = False
        if result:  # if user accepted, go to next step
            step += 1
        else:  # otherwise, go back.
            step -= 1
        if step < 0:  # if user has cancelled out of first dlg
            run = False
        elif step >= len(dialog_classes):  # if user has accepted last dlg
            break

    if run:  # if run is still ongoing
        src_sheet = model[settings[SOURCE_SHEET_KEY]]
        tgt_sheet = model[settings[TARGET_SHEET_KEY]]
        src_sheet.exclusive_editor = True  # nothing should concurrently edit;
        tgt_sheet.exclusive_editor = True  # this allows caching to occur
        translation = Translation(  # create translation
            source_sheet=src_sheet,
            target_sheet=tgt_sheet,
            source_start_row=settings[SOURCE_START_KEY],
            target_start_row=settings[TARGET_START_KEY],
            column_translations=settings[COLUMN_TRANSLATIONS_KEY],
            dialog_parent=dlg,  # there's no way for this to be reached
            #  without dlg being assigned.
            duplicate_action=settings[DUPLICATE_ACTION_KEY],
            whitespace_action=settings[WHITESPACE_ACTION_KEY],
            read_log=settings[LOG_READ_KEY],
            write_log=settings[LOG_WRITE_KEY],
            log_group=settings[LOG_GROUP_KEY],
        )
        translation.commit()  # move cell values

        InfoMessage(  # tell user translation has been applied
            parent=dlg,
            title='Macro Finished',
            main='Finished moving cell values'
        )

    settings.save()  # save settings for next run

model = None
app = None

if __name__ == '__main__':
    lead_app()
