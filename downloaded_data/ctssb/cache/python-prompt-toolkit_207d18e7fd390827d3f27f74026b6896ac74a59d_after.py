"""
Container for the layout.
(Containers can contain other containers or user interface controls.)
"""
from __future__ import unicode_literals

from six import with_metaclass
from abc import ABCMeta, abstractmethod

from .screen import Point, WritePosition
from .dimension import LayoutDimension, sum_layout_dimensions, max_layout_dimensions
from .controls import UIControl
from prompt_toolkit.filters import Filter

__all__ = (
    'HSplit',
    'VSplit',
    'FloatContainer',
    'Float',
    'Window',
)


class Layout(with_metaclass(ABCMeta, object)):
    """
    Base class for user interface layout.
    """
    @abstractmethod
    def reset(self):
        pass

    @abstractmethod
    def width(self, cli):  # XXX: rename to preferred_width
        # Should return a LayoutDimension
        pass

    @abstractmethod  # XXX: rename to preferred_height
    def height(self, cli, width):
        # Should return a LayoutDimension
        pass

    @abstractmethod
    def write_to_screen(self, cli, screen, write_position):
        pass


class HSplit(Layout):
    """
    Several layouts, one stacked above/under the other.
    """
    def __init__(self, children):
        assert all(isinstance(c, Layout) for c in children)
        self.children = children

    def width(self, cli):
        dimensions = [c.width(cli) for c in self.children]
        return max_layout_dimensions(dimensions)

    def height(self, cli, width):
        dimensions = [c.height(cli, width) for c in self.children]
        return sum_layout_dimensions(dimensions)

    def reset(self):
        for c in self.children:
            c.reset()

    def write_to_screen(self, cli, screen, write_position):
        """
        Render the prompt to a `Screen` instance.

        :param screen: The :class:`Screen` class into which we write the output.
        """
        # Calculate heights.
        dimensions = [c.height(cli, write_position.width) for c in self.children]
        sum_dimensions = sum_layout_dimensions(dimensions)

        # If there is not enough space for both.
        # Don't do anything. (TODO: show window to small message.)
        if sum_dimensions.min > write_position.extended_height:
            return

        # Find optimal sizes. (Start with minimal size, increase until we cover
        # the whole height.)
        sizes = [d.min for d in dimensions]

        i = 0
        while sum(sizes) < min(write_position.extended_height, sum_dimensions.preferred):
            # Increase until we meet at least the 'preferred' size.
            if sizes[i] < dimensions[i].preferred:
                sizes[i] += 1
            i = (i + 1) % len(sizes)

        if not any([cli.is_returning, cli.is_exiting, cli.is_aborting]):
            while sum(sizes) < min(write_position.height, sum_dimensions.max):
                # Increase until we use all the available space. (or until "max")
                if sizes[i] < dimensions[i].max:
                    sizes[i] += 1
                i = (i + 1) % len(sizes)

        # Draw child panes.
        ypos = write_position.ypos
        xpos = write_position.xpos
        width = write_position.width

        for s, c in zip(sizes, self.children):
            c.write_to_screen(cli, screen, WritePosition(xpos, ypos, width, s))
            ypos += s


class VSplit(Layout):
    """
    Several layouts, one stacked left/right of the other.
    """
    def __init__(self, children):
        assert all(isinstance(c, Layout) for c in children)
        self.children = children

    def width(self, cli):
        dimensions = [c.width(cli) for c in self.children]
        return sum_layout_dimensions(dimensions)

    def height(self, cli, width):
        sizes = self._divide_widths(cli, width)
        if sizes is None:
            return LayoutDimension()
        else:
            dimensions = [c.height(cli, s) for s, c in zip(sizes, self.children)]
            return max_layout_dimensions(dimensions)

    def reset(self):
        for c in self.children:
            c.reset()

    def _divide_widths(self, cli, width):
        """
        Return the widths for all columns.
        Or None when there is not enough space.
        """
        # Calculate widths.
        dimensions = [c.width(cli) for c in self.children]
        sum_dimensions = sum_layout_dimensions(dimensions)

        # If there is not enough space for both.
        # Don't do anything. (TODO: show window too small message.)
        if sum_dimensions.min > width:
            return

        # TODO: like HSplit, first increase until the "preferred" size.

        # Find optimal sizes. (Start with minimal size, increase until we cover
        # the whole height.)
        sizes = [d.min for d in dimensions]
        i = 0
        while sum(sizes) < min(width, sum_dimensions.max):
            if sizes[i] < dimensions[i].max:
                sizes[i] += 1
            i = (i + 1) % len(sizes)

        return sizes

    def write_to_screen(self, cli, screen, write_position):
        """
        Render the prompt to a `Screen` instance.

        :param screen: The :class:`Screen` class into which we write the output.
        """
        sizes = self._divide_widths(cli, write_position.width)

        if sizes is None:
            return

        # Calculate heights, take the largest possible, but not larger than write_position.extended_height.
        heights = [child.height(cli, width).preferred for width, child in zip(sizes, self.children)]
        height = max(write_position.height, min(write_position.extended_height, max(heights)))

        # Draw child panes.
        ypos = write_position.ypos
        xpos = write_position.xpos

        for s, c in zip(sizes, self.children):
            c.write_to_screen(cli, screen, WritePosition(xpos, ypos, s, height))
            xpos += s


class FloatContainer(Layout):
    """
    Container which can contain another container for the background, as well
    as a list of floating containers on top of it.

    Example Usage::

        FloatContainer(content=Window(...),
                       floats=[
                           Float(xcursor=True,
                                ycursor=True,
                                layout=CompletionMenu(...))
                       ])
    """
    def __init__(self, content, floats):
        assert isinstance(content, Layout)
        assert all(isinstance(f, Float) for f in floats)

        self.content = content
        self.floats = floats

    def reset(self):
        self.content.reset()

    def width(self, cli):
        return self.content.width(cli)

    def height(self, cli, width):
        """
        Return the preferred height of the float container.
        (We don't care about the height of the floats, they should always fit
        into the dimensions provided by the container.)
        """
        return self.content.height(cli, width)

    def write_to_screen(self, cli, screen, write_position):
        self.content.write_to_screen(cli, screen, write_position)

        # When a menu_position was given, use this instead of the cursor
        # position. (These cursor positions are absolute, translate again
        # relative to the write_position.)
        cursor_position = screen.menu_position or screen.cursor_position
        cursor_position = Point(x=cursor_position.x - write_position.xpos,
                                y=cursor_position.y - write_position.ypos)

        for fl in self.floats:
            # Left & width given.
            if fl.left is not None and fl.width is not None:
                xpos = fl.left
                width = fl.width
            # Left & right given -> calculate width.
            elif fl.left is not None and fl.right is not None:
                xpos = fl.left
                width = write_position.width - fl.left - fl.right
            # Width & right given -> calculate left.
            elif fl.width is not None and fl.right is not None:
                xpos = write_position.width - fl.right - fl.width
                width = fl.width
            elif fl.xcursor:
                width = fl.width
                if width is None:
                    width = fl.content.width(cli).preferred

                xpos = cursor_position.x
                if xpos + width > write_position.width:
                    xpos = max(0, write_position.width - width)
            else:
                xpos = 0
                width = write_position.width

            # Top & height given.
            if fl.top is not None and fl.height is not None:
                ypos = fl.top
                height = fl.height
            # Top & bottom given -> calculate height.
            elif fl.top is not None and fl.bottom is not None:
                ypos = fl.top
                height = write_position.height - fl.top - fl.bottom
            # Height & bottom given -> calculate top.
            elif fl.height is not None and fl.bottom is not None:
                ypos = write_position.height - fl.height - fl.bottom
                height = fl.height
            # Near cursor
            elif fl.ycursor:
                ypos = cursor_position.y + 1

                height = fl.height
                if height is None:
                    height = fl.content.height(cli, width).preferred

                # Reduce height if not enough space. (We can use the
                # extended_height when the content requires it.)
                if height > write_position.extended_height - ypos:
                    height = write_position.extended_height - ypos
            else:
                ypos = 0
                height = write_position.height

            # Write float.
            if xpos >= 0 and ypos >= 0 and height > 0 and width > 0:
                wp = WritePosition(xpos=xpos + write_position.xpos,
                                   ypos=ypos + write_position.ypos,
                                   width=width, height=height)
                fl.content.write_to_screen(cli, screen, wp)


class Float(object):
    def __init__(self, top=None, right=None, bottom=None, left=None,
                 width=None, height=None,
                 xcursor=False, ycursor=False, content=None):
        assert isinstance(content, Layout)

        self.left = left
        self.right = right
        self.top = top
        self.bottom = bottom

        self.width = width
        self.height = height

        self.xcursor = xcursor
        self.ycursor = ycursor

        self.content = content


class Window(Layout):
    """
    Layout that holds a control.

    :param content: User interface control.
    :param width: `LayoutDimension` instance.
    :param height: `LayoutDimension` instance.
    :param get_width: callable which takes a `CommandLineInterface` and returns a `LayoutDimension`.
    :param get_height: callable which takes a `CommandLineInterface` and returns a `LayoutDimension`.
    :param filter: `Filter` which decides about the visibility.
    :param dont_extend_width: When `True`, don't take up more width then the
                              preferred width reported by the control.
    :param dont_extend_height: When `True`, don't take up more width then the
                               preferred height reported by the control.
    """
    def __init__(self, content, width=None, height=None, get_width=None,
                 get_height=None, filter=None, dont_extend_width=False,
                 dont_extend_height=False):
        assert isinstance(content, UIControl)
        assert width is None or isinstance(width, LayoutDimension)
        assert height is None or isinstance(height, LayoutDimension)
        assert get_width is None or callable(get_width)
        assert get_height is None or callable(get_height)
        assert width is None or get_width is None
        assert height is None or get_height is None
        assert filter is None or isinstance(filter, Filter)

        self.content = content
        self.filter = filter
        self.dont_extend_width = dont_extend_width
        self.dont_extend_height = dont_extend_height
        self._width = get_width or (lambda cli: width)
        self._height = get_height or (lambda cli: height)

        self.reset()

    def __repr__(self):
        return 'Window(content=%r)' % self.content

    def reset(self):
        self.content.reset()

        #: Vertical scrolling position of the main content.
        self.vertical_scroll = 0

    def _visible(self, cli):
        return self.filter is None or self.filter(cli)

    def width(self, cli):
        if self._visible(cli):
            width = self._width(cli) or LayoutDimension()
            preferred_width = self.content.preferred_width(cli)

            if preferred_width is None:
                return width
            else:
                # When 'dont_extend_width' has been given. Don't use more than
                # the preferred width of the control. (But also don't go below
                # the minimum.)
                if self.dont_extend_width:
                    max_width = max(width.min, min(preferred_width, width.max))
                else:
                    max_width = width.max
                return LayoutDimension(min=width.min, max=max_width, preferred=preferred_width)
        else:
            return LayoutDimension.exact(0)

    def height(self, cli, width):
        if self._visible(cli):
            height = self._height(cli) or LayoutDimension()
            preferred_height = self.content.preferred_height(cli, width)

            if preferred_height is None:
                return height
            else:
                # When 'dont_extend_height' has been given. Don't use more than
                # the preferred height of the control. (But also don't go below
                # the minimum.)
                if self.dont_extend_height:
                    max_height = max(height.min, min(preferred_height, height.max))
                else:
                    max_height = height.max
                return LayoutDimension(min=height.min, max=max_height, preferred=preferred_height)
        else:
            return LayoutDimension.exact(0)

    def write_to_screen(self, cli, screen, write_position):
                        # XXX: Show window too small messsage...

        # Only write when visible.
        if self._visible(cli):
            # Set position.
            temp_screen = self.content.create_screen(cli, write_position.width, write_position.height)
            self._scroll(temp_screen, write_position.height)
            self._copy(cli, temp_screen, screen, write_position)

    def _copy(self, cli, temp_screen, new_screen, write_position):
        """
        Copy characters from the temp screen that we got from the `UIControl`
        to the real screen.
        """
        xpos = write_position.xpos
        ypos = write_position.ypos
        width = write_position.width
        height = write_position.height

        columns = temp_screen.width

        temp_buffer = temp_screen._buffer
        new_buffer = new_screen._buffer
        temp_screen_height = temp_screen.current_height
        y = 0

        # Now copy the region we need to the real screen.
        for y in range(0, height):
            # We keep local row variables. (Don't look up the row in the dict
            # for each iteration of the nested loop.)
            new_row = new_buffer[y + ypos]

            if y >= temp_screen_height and y >= write_position.height:
                # Break out of for loop when we pass after the last row of the
                # temp screen. (We use the 'y' position for calculation of new
                # screen's height.)
                break
            else:
                temp_row = temp_buffer[y + self.vertical_scroll]
                for x in range(0, columns):
                    new_row[x + xpos] = temp_row[x]

        if self.content.has_focus(cli):
            new_screen.cursor_position = Point(y=temp_screen.cursor_position.y + ypos - self.vertical_scroll,
                                               x=temp_screen.cursor_position.x + xpos)

        if not new_screen.menu_position and temp_screen.menu_position:
            new_screen.menu_position = Point(y=temp_screen.menu_position.y + ypos - self.vertical_scroll,
                                             x=temp_screen.menu_position.x + xpos)

        # Update height of this screen.
        new_screen.current_height = max(new_screen.current_height, ypos + y + 1)

    def _scroll(self, temp_screen, height):
        """
        Scroll to make sure the cursor position is visible.
        """
        # Scroll back if we scrolled to much and there's still space at the top.
        if self.vertical_scroll > temp_screen.current_height - height:
            self.vertical_scroll = max(0, temp_screen.current_height - height)

        # Scroll up if cursor is before visible part.
        if self.vertical_scroll > temp_screen.cursor_position.y:
            self.vertical_scroll = temp_screen.cursor_position.y

        # Scroll down if cursor is after visible part.
        if self.vertical_scroll <= temp_screen.cursor_position.y - height:
            self.vertical_scroll = (temp_screen.cursor_position.y + 1) - height
