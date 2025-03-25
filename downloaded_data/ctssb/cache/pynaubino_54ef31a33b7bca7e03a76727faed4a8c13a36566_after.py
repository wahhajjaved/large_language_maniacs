import pymunk
from pymunk import Vec2d
from Space import Space
from Pointer import Pointer
from PyQt4.QtCore import *
from PyQt4.QtGui import QColor
from utils import Pos, random_vec
from Naub import Naub
from Menu import NaubinoMenu
from random import sample, random
import math

class Naubino(object):
    @property
    def score(self): return self.__score
    @score.setter
    def score(self, score):
        if self.__score == score: return
        self.__score = score
        if self.score_changed: self.score_changed(score)

    @property
    def warn(self): return self.__warn
    @warn.setter
    def warn(self, warn):
        if self.__warn == warn: return
        self.__warn = warn
        if self.warn_changed: self.warn_changed(warn)
    
    def __init__(self, app = None):
        self.naubs = []
        self.naubjoints = set()
        self.naub_center_joints = {}
        self.playing = False
        self.app = app
        self.scene = scene = app.scene
        self.__score = 0
        self.score_changed = None
        self.__warn = False
        self.warn_changed = None
        self.fail = None
        
        self.naub_colors = {
            "red":    [229,  53,  23],
            "pink":   [226,   0, 122],
            "green":  [151, 190,  13],
            "blue":   [  0, 139, 208],
            "purple": [100,  31, 128],
            "yellow": [255, 204,   0]}
        self.colors = {
            "black":  [  0,   0,   0],
            "grey":   [160, 160, 160],
            "white":  [255, 255, 255]}
        self.colors.update(self.naub_colors)    

        interval = 1 / 50.0
        def callback(): self.step(interval)
        self.stepper = app.Timer(interval, callback)
        
        pymunk.init_pymunk()
        space = self.space = Space()

        pointer = self.pointer = Pointer()
        space.add(pointer.body)

        center = self.center = pymunk.Body(pymunk.inf, pymunk.inf)
        center.position = 0, 0

        self.spammer = app.Timer(1, self.spam_naub_pair)

        if scene: scene.naubino = self

    def add_item(self, *items):
        if self.scene: self.scene.add_item(*items)

    def remove_item(self, *items):
        if self.scene: self.scene.remove_item(*items)

    def add_naub(self, naub):
        naub.naubino = self

        if naub not in self.naubs:
            self.naubs.append(naub)

        if naub not in self.naub_center_joints:
            a = naub.body
            b = self.center
            anchor = 0, 0
            joint = pymunk.PinJoint(a, b, anchor, anchor)
            joint.distance = 0
            joint.bias_coef
            joint.max_bias = 18
            joint.max_force = 100
            self.naub_center_joints[naub] = joint
            self.space.add(joint)

        if self.scene: self.scene.add_naub(naub)

    def remove_naub(self, naub):
        if self.scene: self.scene.remove_naub(naub)
            
        if naub in self.naub_center_joints:
            joint = self.naub_center_joints[naub]
            del self.naub_center_joints[naub]
            self.space.remove(joint)

        if naub in self.naubs:
            self.naubs.remove(naub)

    def pre_remove_naub(self, naub):
        if self.scene: self.scene.pre_remove_naub(naub)

    def add_naubs(self, *naubs):
        for naub in naubs: self.add_naub(naub)

    def add_naub_joint(self, joint):
        self.naubjoints.add(joint)
        if self.scene: self.scene.add_naub_joint(joint)

    def remove_naub_joint(self, joint):
        self.naubjoints.discard(joint)
        if self.scene: self.scene.remove_naub_joint(joint)

    def pre_remove_naub_joint(self, joint):
        if self.scene: self.scene.pre_remove_naub_joint(joint)

    def create_naub_pair(self, pos = (0, 0), rot = 0):
        pos = Vec2d(pos)
        a = Vec2d(-1, 0)
        b = Vec2d( 1, 0)
        a.rotate(rot)
        b.rotate(rot)
        a += pos
        b += pos
        a = Naub(self, a)
        b = Naub(self, b)
        self.add_naub(a)
        self.add_naub(b)
        a.join_naub(b)
        return a, b

    def spam_naub_pair(self):
        pos = self.random_naub_pos()
        rot = random() * math.pi * 2
        a, b = self.create_naub_pair(pos, rot)

        impulse = lambda: random_vec(50, 50)
        a.body.apply_impulse(impulse())
        b.body.apply_impulse(impulse())

        a.color = self.random_naub_color()
        b.color = self.random_naub_color()

        self.add_naubs(a, b)

    def random_naub_pos(self):
        a = Vec2d(350, 0)
        b = Vec2d(0, 220)
        if random() < 0.5:
            a,b = b,a
        if random() < 0.5:
            b = -b
        return random_vec(a.x, a.y) + b

    def random_naub_color(self):
        colors = self.naub_colors
        color = colors[sample(colors, 1)[0]]
        return QColor(*color)

    def score_cycle(self, cycle):
        # self.score += len(cycle)
        # property can't do +=
        self.score = self.score + len(cycle)

    def step(self, dt):
        self.space.step(dt)
        if self.scene: self.scene.step(dt)
        danger = self.danger()
        self.warn = False if danger < 30 else True
        if danger > 40:
            self.stop()
            if self.fail: self.fail()

    def danger(self):
        danger = 0
        for j in self.naubjoints:
            if (j.a.pos.get_length() < 160
            or  j.b.pos.get_length() < 160):
                danger += 1
        return danger

    def play(self):
        self.spammer.start()
        self.stepper.start()

    def stop(self):
        self.spammer.stop()
        self.stepper.stop()