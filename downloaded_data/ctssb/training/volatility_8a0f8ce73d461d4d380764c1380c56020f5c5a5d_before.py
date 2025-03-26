import math
from volatility.fmtspec import FormatSpec

__author__ = 'mike'

from volatility import renderers

class Address(int):
    """Integer class to allow renderers to differentiate between addresses and numbers"""
    def __new__(cls, number):
        return int.__new__(cls, number)

class Address64(int):
    """Integer class to allow renderers to differentiate between addresses and numbers"""

    def __new__(cls, number):
        return int.__new__(cls, number)


class Hex(int):
    """Integer class to allow renderers to differentiate between addresses and numbers"""

    def __new__(cls, number):
        return int.__new__(cls, number)

class CellRenderer(object):
    """Class to handle rendering of a particular cell in a text grid"""
    # The minimum width that the renderer will produce for a value
    width = 0

    def render(self, value):
        """Returns the rendering of an individual value"""
        return value

class FormatCellRenderer(CellRenderer):
    """Class to handle rendering each cell of a grid"""

    def __init__(self, format_spec):
        if not isinstance(format_spec, FormatSpec):
            fs = FormatSpec()
            fs.from_string(format_spec)
            format_spec = fs
        self._format_spec = format_spec

    def render(self, value):
        """Render an individual cell"""
        return ("{0:" + str(self._format_spec) + "}").format(value)

    @property
    def width(self):
        return self._format_spec.minwidth

    @width.setter
    def width(self, value):
        self._format_spec.minwidth = max(value, self._format_spec.minwidth)

    def __repr__(self):
        return "<FormatCellRenderer (" + repr(self._format_spec) + ")>"

class TextRenderer(object):

    min_column_width = 5

    def __init__(self, cell_renderers, max_width = 200):

        if not isinstance(cell_renderers, list):
            raise TypeError("cell_renderers must be of type list")
        for item in cell_renderers:
            if not isinstance(item, CellRenderer):
                raise TypeError("Items within the cell_renderers list must be of type CellRenderer")
        self._cell_renderers = cell_renderers
        self.max_width = max_width

    def partition_width(self, widths):
        """Determines if the widths are over the maximum available space, and if so shrinks them"""
        if math.fsum(widths) + (len(widths) - 1) > self.max_width:
            remainder = (int(math.fsum(widths)) + (len(widths) - 1)) - self.max_width
            # Take from the largest column first, eventually evening out
            for i in range(remainder):
                col_index = widths.index(max(widths))
                widths[col_index] -= 1
        return widths

    def _elide(self, string, length):
        """Ensures that strings passed as value are returned no longer than max_width characters long, elided if necessary"""
        if length == -1:
            return string
        if len(string) < length:
            return (" " * (length - len(string))) + string
        elif len(string) == length:
            return string
        else:
            if length < self.min_column_width:
                return string
            even = ((length + 1) % 2)
            length = (length - 3) / 2
            return string[:length + even] + "..." + string[-length:]


    def render(self, fdout, grid):
        """Renders a text grid based on the contents of each element"""
        if not isinstance(grid, renderers.TreeGrid):
            raise TypeError("Grid must be of type TreeGrid")
        if len(grid.columns) != len(self._cell_renderers):
            raise ValueError("The number of cell_renderers (" + len(self._cell_renderers) +
                             ") must match the number of columns in the grid (" + len(grid.columns) + ").")

        # Determine number of columns
        grid_depth = grid.visit(None, lambda x, y: max(y, grid.path_depth(x)), 0)

        # Determine max width of each column
        grid_max_widths = [0] * len(grid.columns)

        def gridwidth(node, accumulator = None):
            for vindex in range(len(node.values)):
                entry = self._cell_renderers[vindex].render(node.values[vindex])
                accumulator[vindex] = max(len(entry), accumulator[vindex])
            return accumulator

        grid.visit(None, gridwidth, grid_max_widths)
        if grid_depth > 1:
            grid_max_widths = [grid_depth * 1] + grid_max_widths

        # Figure out how to partition the available widths
        new_grid_widths = self.partition_width(grid_max_widths)

        # If the grid_max_widths have not been limited,
        if new_grid_widths == grid_max_widths:
            for i in range(len(grid.columns)):
                index = i + (1 if grid_depth > 1 else 0)
                grid_max_widths[index] = max(grid_max_widths[index], len(grid.columns[i].name))

        for i in range(len(grid.columns)):
            index = i + (1 if grid_depth > 1 else 0)
            self._cell_renderers[i].width = grid_max_widths[index]
            grid_max_widths[index] = self._cell_renderers[i].width

        cols = []
        for index in range(len(grid_max_widths)):
            if grid_depth > 1:
                if index != 0:
                    cols += [" " * grid_max_widths[index]]
                    continue
                else:
                    column = grid.columns[index - 1]
            else:
                column = grid.columns[index]
            cols += [self._elide(("{:<" + str(grid_max_widths[index]) + "}").format(column.name), grid_max_widths[index])]
        fdout.write(" ".join(cols) + "\n")

        def print_row(node, accumulator = None):
            row = []
            for index in range(len(grid_max_widths)):
                if grid_depth > 1:
                    if index == 0:
                        row += [(" " * (grid.path_depth(node) - 1)) + ">" + (" " * (grid_max_widths[0] - grid.path_depth(node)))]
                        continue
                    else:
                        column = grid.columns[index - 1]
                else:
                    column = grid.columns[index]

                column_text = self._cell_renderers[column.index].render(node.values[column.index])
                row += [self._elide(column_text, grid_max_widths[index])]
            accumulator += [" ".join(row)]
            return accumulator

        output = []
        grid.visit(None, print_row, output)
        fdout.write("\n".join(output) + "\n")
