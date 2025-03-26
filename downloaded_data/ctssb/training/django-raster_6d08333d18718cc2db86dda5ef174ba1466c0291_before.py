import numpy
from PIL import Image

from raster.algebra.parser import FormulaParser
from raster.exceptions import RasterException

IMG_FORMATS = {'.png': 'PNG', '.jpg': 'JPEG'}


def hex_to_rgba(value, alpha=255):
    """
    Converts a HEX color string to a RGBA 4-tuple.
    """
    value = value.lstrip('#')

    # Check length and input string property
    if len(value) not in [1, 2, 3, 6] or not value.isalnum():
        raise RasterException('Invalid color, could not convert hex to rgb.')

    # Repeat values for shortened input
    value = (value * 6)[:6]

    # Convert to rgb
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha


def band_data_to_image(band_data, colormap):
    """
    Creates an python image from pixel values of a GDALRaster.
    The input is a dictionary that maps pixel values to RGBA UInt8 colors.
    """
    parser = FormulaParser()

    # Get data as 1D array
    dat = band_data.ravel()

    # Create zeros array
    rgba = numpy.zeros((dat.shape[0], 4), dtype='uint8')

    # Replace matched rows with colors
    stats = {}
    for key, color in colormap.items():
        orig_key = key
        try:
            # Try to use the key as number directly
            key = float(key)
            selector = dat == key
            rgba[selector] = color
        except ValueError:
            # Otherwise use it as numpy expression directly
            selector = parser.evaluate(key, {'x': dat})
            rgba[selector] = color
        stats[orig_key] = int(numpy.sum(selector))

    # Reshape array to image size
    rgba = rgba.reshape(band_data.shape[0], band_data.shape[1], 4)

    # Create image from array
    img = Image.fromarray(rgba)

    return img, stats
