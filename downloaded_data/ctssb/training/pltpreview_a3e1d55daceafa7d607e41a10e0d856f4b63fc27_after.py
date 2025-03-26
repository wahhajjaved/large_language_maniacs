"""Convenience functions for matplotlib plotting and image viewing."""
import numpy as np
from matplotlib import pyplot as plt, cm


def show(image, block=False, title='', **kwargs):
    """Show *image*. If *block* is False the call is nonblocking. *title*
    is the image title.  *kwargs* are passed to matplotlib's ``imshow``
    function. This command always creates a new figure. Returns matplotlib's
    ``AxesImage``.
    """
    plt.figure()

    if 'cmap' not in kwargs:
        kwargs['cmap'] = cm.gray
    if 'interpolation' not in kwargs:
        kwargs['interpolation'] = 'nearest'

    mpl_image = plt.imshow(image, **kwargs)
    mpl_image.axes.format_coord = _FormatCoord(image)
    plt.colorbar(ticks=np.linspace(image.min(), image.max(), 8))
    plt.title(title)
    plt.show(block)

    return mpl_image


def plot(*args, **kwargs):
    """Plot using matplotlib's ``plot`` function. Pass it *args* and *kwargs*.  *kwargs* are
    infected with *block* and if False or not specified, the call is nonblocking. *title* is alowed
    to be in *kwargs* which sets the figure title. *grid* can be in kwargs which is a boolean
    turning the grid on or off. *xlabel* and *ylabel* define the x and y axes labels if specified in
    *kwargs*. This command always creates a new figure. Returns a list of ``Line2D`` instances.
    """
    block = kwargs.pop('block', False)
    title = kwargs.pop('title', '')
    xlabel = kwargs.pop('xlabel', '')
    ylabel = kwargs.pop('ylabel', '')
    grid = kwargs.pop('grid', True)

    plt.figure()
    lines = plt.plot(*args, **kwargs)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(grid)
    plt.show(block)

    return lines


class _FormatCoord(object):
    """Coordinates formatter."""
    def __init__(self, image):
        self.image = image
        self.height, self.width = self.image.shape
        self.value_fmt = determine_intensity_format(self.image[0, 0])

    def __call__(self, x, y):
        """Overrides matplotlib's default behavior on mouse motion,
        *x* and *y* are planar coordinates.
        """
        col = int(x + 0.5)
        row = int(y + 0.5)

        if col >= 0 and col < self.width and row >= 0 and row < self.height:
            # The formatting doesn't like np.float32
            value = float(self.image[row, col])
            value_str = self.value_fmt.format(value)
            return 'x={:<12.2f}y={:<12.2f}{}'.format(x, y, value_str)
        else:
            return 'x={:<12.2f}y={:<12.2f}'.format(x, y)


def determine_intensity_format(number):
    """Get format string based on *number*'s data type."""
    if isinstance(number, (float, np.float, np.float16, np.float32,
                           np.float64, np.float128)):
        fmt = 'I={:<12.5f}'
    else:
        fmt = 'I={:<12}'

    return fmt
