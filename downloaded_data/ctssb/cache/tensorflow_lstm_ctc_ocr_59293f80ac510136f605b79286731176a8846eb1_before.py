#!/usr/bin/env python
#
# Copyright (c) 2016 Matthew Earl
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
#     The above copyright notice and this permission notice shall be included
#     in all copies or substantial portions of the Software.
# 
#     THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
#     OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
#     MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
#     NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
#     DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#     OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
#     USE OR OTHER DEALINGS IN THE SOFTWARE.



"""
Generate training and test images.

"""

__all__ = (
    'generate_ims',
)

import math
import os
import random
import sys

import cv2
import numpy

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

import cPickle as pickle

import common
from common import OUTPUT_SHAPE

fonts = [ "fonts/Arial.ttf", "fonts/times.ttf", "fonts/msyh.ttf"]
# fonts = ["fonts/Farrington-7B-Qiqi.ttf","fonts/times.ttf"]
FONT_HEIGHT = 32  # Pixel size to which the chars are resized

CHARS = common.CHARS + " "


def make_char_ims(output_height, font):
    font_size = output_height * 4
    font = ImageFont.truetype(font, font_size)
    height = max(font.getsize(d)[1] for d in CHARS)
    for c in CHARS:
        width = font.getsize(c)[0]
        im = Image.new("RGBA", (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(im)
        draw.text((0, 0), c, (255, 255, 255), font=font)
        scale = float(output_height) / height
        im = im.resize((int(width * scale), output_height), Image.ANTIALIAS)
        char_array = numpy.array(im)[:, :, 0].astype(numpy.float32) / 255.
        #print(char_array)
        for idx in range(0, char_array.shape[0]):
            for idy in range(0, char_array.shape[1]):
                if char_array[idx][idy] >= 150.0/255.0:
                    char_array[idx][idy] = 1
                else:
                    char_array[idx][idy] = 0
        yield c, char_array


def get_all_font_char_ims(out_height):
    result = []
    for font in fonts:
        result.append(dict(make_char_ims(out_height, font)))
    return result

def euler_to_mat(yaw, pitch, roll):
    # Rotate clockwise about the Y-axis
    c, s = math.cos(yaw), math.sin(yaw)
    M = numpy.matrix([[c, 0., s],
                      [0., 1., 0.],
                      [-s, 0., c]])

    # Rotate clockwise about the X-axis
    c, s = math.cos(pitch), math.sin(pitch)
    M = numpy.matrix([[1., 0., 0.],
                      [0., c, -s],
                      [0., s, c]]) * M

    # Rotate clockwise about the Z-axis
    c, s = math.cos(roll), math.sin(roll)
    M = numpy.matrix([[c, -s, 0.],
                      [s, c, 0.],
                      [0., 0., 1.]]) * M

    return M


def pick_colors():
    first = True
    #return random.random(),random.random()
    #while first or plate_color - text_color < 0.9:
    while first:
        text_color = random.uniform(0.4, 1)
        #text_color = 1
        plate_color = random.random()
        #if text_color > plate_color:
        #    text_color, plate_color = plate_color, text_color
        first = False
    return text_color, plate_color


def make_affine_transform(from_shape, to_shape,
                          min_scale, max_scale,
                          scale_variation=1.0,
                          rotation_variation=1.0,
                          translation_variation=1.0):
    out_of_bounds = False

    from_size = numpy.array([[from_shape[1], from_shape[0]]]).T
    to_size = numpy.array([[to_shape[1], to_shape[0]]]).T

    scale = random.uniform((min_scale + max_scale) * 0.5 -
                           (max_scale - min_scale) * 0.5 * scale_variation,
                           (min_scale + max_scale) * 0.5 +
                           (max_scale - min_scale) * 0.5 * scale_variation)
    if scale > max_scale or scale < min_scale:
        out_of_bounds = True
    roll = random.uniform(-0.3, 0.3) * rotation_variation
    pitch = random.uniform(-0.2, 0.2) * rotation_variation
    yaw = random.uniform(-1.2, 1.2) * rotation_variation

    # Compute a bounding box on the skewed input image (`from_shape`).
    M = euler_to_mat(yaw, pitch, roll)[:2, :2]
    h, w = from_shape
    corners = numpy.matrix([[-w, +w, -w, +w],
                            [-h, -h, +h, +h]]) * 0.5
    skewed_size = numpy.array(numpy.max(M * corners, axis=1) -
                              numpy.min(M * corners, axis=1))

    # Set the scale as large as possible such that the skewed and scaled shape
    # is less than or equal to the desired ratio in either dimension.
    scale *= numpy.min(to_size / skewed_size) * 1.1

    # Set the translation such that the skewed and scaled image falls within
    # the output shape's bounds.
    trans = (numpy.random.random((2, 1)) - 0.5) * translation_variation
    trans = ((2.0 * trans) ** 5.0) / 2.0
    if numpy.any(trans < -0.5) or numpy.any(trans > 0.5):
        out_of_bounds = True
    trans = (to_size - skewed_size * scale) * trans

    center_to = to_size / 2.
    center_from = from_size / 2.

    M = euler_to_mat(yaw, pitch, roll)[:2, :2]
    M *= scale
    M = numpy.hstack([M, trans + center_to - M * center_from])
    return M, out_of_bounds


def generate_code():
    f = ""
    append_blank = random.choice([True, False])
    length = random.choice(range(0,21))
    blank = ''
    if common.ADD_BLANK:
        blank = ' '

    for i in range(length):
        if 0 == i % 4 and append_blank and i > 0:  # do not add blank as the first digit
            f = f + blank
        f = f + random.choice(common.DIGITS)
    return f


def rounded_rect(shape, radius):
    out = numpy.ones(shape)
    out[:radius, :radius] = 0.0
    out[-radius:, :radius] = 0.0
    out[:radius, -radius:] = 0.0
    out[-radius:, -radius:] = 0.0

    cv2.circle(out, (radius, radius), radius, 1.0, -1)
    cv2.circle(out, (radius, shape[0] - radius), radius, 1.0, -1)
    cv2.circle(out, (shape[1] - radius, radius), radius, 1.0, -1)
    cv2.circle(out, (shape[1] - radius, shape[0] - radius), radius, 1.0, -1)

    return out


def generate_plate(font_height, char_ims):
    h_padding = random.uniform(0, 0.4) * font_height
    v_padding = random.uniform(0, 0.3) * font_height
    spacing = font_height * random.uniform(0.01, 0.05)
    radius = 1 + int(font_height * 0.1 * random.random())
    code = generate_code()
    text_width = sum(char_ims[c].shape[1] for c in code)
    text_width += (len(code) - 1) * spacing

    out_shape = (int(font_height + v_padding * 2),
                 int(text_width + h_padding * 2))

    #text_color, plate_color = pick_colors()
    text_color = 1
    
    text_mask = numpy.zeros(out_shape)

    x = h_padding
    y = v_padding
    for c in code:
        char_im = char_ims[c]
        ix, iy = int(x), int(y)
        text_mask[iy:iy + char_im.shape[0], ix:ix + char_im.shape[1]] = char_im
        x += char_im.shape[1] + spacing

    plate = (  # numpy.ones(out_shape) * plate_color * (1. - text_mask) +
        # numpy.ones(out_shape) *
        text_color * text_mask)

    # print "fffff", plate.shape
    # plate.resize([plate.shape[0] + 3, plate.shape[1]+1 ])
    # cv2.imwrite("test/fff.png", plate * 255)
    return plate, rounded_rect(out_shape, radius), code  # means blank


def generate_bg(bg_ims):
    index = random.randint(0, len(bg_ims)-1)
    bg = bg_ims[index]
    x = random.randint(0, bg.shape[1] - OUTPUT_SHAPE[1])
    y = random.randint(0, bg.shape[0] - OUTPUT_SHAPE[0])
    bg = bg[y:y + OUTPUT_SHAPE[0], x:x + OUTPUT_SHAPE[1]]

    return bg
    
def get_all_bg_ims(num_bg_images):
    result = []
    for i in range(0, num_bg_images):
        fname = "bgs/{:08d}.jpg".format(i)
        bg = cv2.imread(fname, 0) / 255.
        if (bg.shape[1] < OUTPUT_SHAPE[1] or
                    bg.shape[0] < OUTPUT_SHAPE[0]):
            continue;
        result.append(bg)
    return result

def generate_im(char_ims, bg_ims):
    bg = generate_bg(bg_ims)

    plate, plate_mask, code = generate_plate(FONT_HEIGHT, char_ims)

    M, out_of_bounds = make_affine_transform(
        from_shape=plate.shape,
        to_shape=bg.shape,
        min_scale=0.7,
        max_scale=0.9,
        rotation_variation=0.20,
        scale_variation=1.0,
        translation_variation=1.0)
    plate = cv2.warpAffine(plate, M, (bg.shape[1], bg.shape[0]))
    plate_mask = cv2.warpAffine(plate_mask, M, (bg.shape[1], bg.shape[0]))
    # plate_mask = cv2.warpAffine(plate_mask, M, (bg.shape[1], bg.shape[0]))

    # out = plate * plate_mask + bg * (1 - plate_mask)
    out = plate + bg
    # out = plate
    out = cv2.resize(out, (OUTPUT_SHAPE[1], OUTPUT_SHAPE[0]))

    # out += numpy.random.normal(scale=0.05, size=out.shape)
    out = numpy.clip(out, 0., 1.)
    return out, code, not out_of_bounds


def generate_ims(num_images):
    """
    Generate a number of number plate images.

    :param num_images:
        Number of images to generate.

    :return:
        Iterable of number plate images.

    """
    char_ims = get_all_font_char_ims(FONT_HEIGHT)
    num_bg_images = len(os.listdir("bgs")) - 2
    bg_ims = get_all_bg_ims(num_bg_images)
    for i in range(num_images):
        yield generate_im(random.choice(char_ims), bg_ims)

#if __name__ == "__main__":
def gen_all():
    dirs = ["test", "train"]
    size = {"test": common.TEST_SIZE, "train": common.TRAIN_SIZE}
    for dir_name in dirs:
	labels = {}
        if not os.path.exists(dir_name):
            os.mkdir(dir_name)
        im_gen = generate_ims(size.get(dir_name))
        for img_idx, (im, c, p) in enumerate(im_gen):
            fname = dir_name + "/{:08d}_{}.png".format(img_idx, "1" if p else "0")
            print '\'' + fname + '\','
            cv2.imwrite(fname, im * 255.)
            label_idx = "{:08d}".format(img_idx)
            labels[label_idx] = c
	label_file = open(dir_name + '_label.txt', 'w')
	pickle.dump(labels, label_file)
	label_file.close()	
