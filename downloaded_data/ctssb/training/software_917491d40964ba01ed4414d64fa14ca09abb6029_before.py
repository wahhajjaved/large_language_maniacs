import math
from collections import namedtuple

from .camera import Camera
from .colors import Colors
from .blobdetection import BlobDetector
from .thresholding import ColorDetectResult
from .window import Window

import numpy as np
class Cube(namedtuple('Cube', 'pos color')):
    @property
    def angle_to(self):
        """ Planar angle """
        return math.atan2(self.pos[0], self.pos[1])

    @property
    def distance(self):
        """ Planar distance """
        return np.linalg.norm(self.pos[:2])

    def __str__(self):
        return "<{} cube at {:.1f}, {:.1f}, {:.1f}>".format(Colors.name(self.color), self.pos[0], self.pos[1], self.pos[2])


class Vision(object):
    """Takes an image and returns the angle to blobs"""

    def __init__(self, cam):
        self.cam = cam
        self.ray = None
        self.angle_to = None
        self.debug_win = Window('vision debug')

    def update(self):
        self.frame = self.cam.read()
        self.color_detect = ColorDetectResult(self.frame)
        red_blobs = BlobDetector(self.color_detect, Colors.RED, 100).blobs
        green_blobs = BlobDetector(self.color_detect, Colors.GREEN, 100).blobs

        all_blobs = red_blobs + green_blobs

        # TODO:
        #   filter out cubes above the wall
        #   detect cubes in a stack
        #   look at cube area

        self.cubes = [
            Cube(
                pos=self.cam.geom.project_on(
                    ray=self.cam.geom.ray_at(blob.pos[1], blob.pos[0]),
                    normal=[0, 0, 1, 0],
                    d=1  # center of the cube is 1in off the ground
                ),
                color=blob.color
            )
            for blob in all_blobs
        ]

        self.debug_win.show(self.color_detect.debug_frame)

    def nearest_cube(self, color=None):
        """ get the nearest cube, by cartesian distance, optionally of a specific color """
        filtered = self.cubes
        if color is not None:
            filtered = (c for c in self.cubes if c.color == color)

        try:
            return max(filtered, key=lambda c: c.distance)
        except ValueError:
            return None