#!/usr/bin/env python3
import asyncio
import uuid
import json
from datetime import datetime

import logging

import math

from random import randint, shuffle
from simple_commander.utils.line_intersection import object_intersection, point_distance

'''
In this game we have two role - invader and hero. Both can bullet.

Invaders are located at the top of game field and always move from the right side to the left and revert.
Also they slowly move to the bottom.

Main hero is located at the centre at the bottom. He can move to the left and to the right.
If he bullet some invader, his bonus is grow.
When invader bullet to main hero, the main hero's life is decrease.
'''

UNITS = {'invader': [{'type': 'invader1', 'dimension': 28},
                     {'type': 'invader2', 'dimension': 28},
                     {'type': 'invader3', 'dimension': 28}],
         'hero': [{'type': 'hero_1_black', 'dimension': 28},
                  {'type': 'hero_1_green', 'dimension': 28},
                  {'type': 'hero_1_blue', 'dimension': 28},
                  {'type': 'hero_1_pink', 'dimension': 28},
                  {'type': 'hero_1_white', 'dimension': 28},
                  {'type': 'hero_1_red', 'dimension': 28},
                  {'type': 'hero_2_black', 'dimension': 28},
                  {'type': 'hero_2_green', 'dimension': 28},
                  {'type': 'hero_2_blue', 'dimension': 28},
                  {'type': 'hero_2_pink', 'dimension': 28},
                  {'type': 'hero_2_white', 'dimension': 28},
                  {'type': 'hero_2_red', 'dimension': 28}],
         'bullet_hero': {'type': 'bullet_hero', 'dimension': 10},
         'bullet_invader': {'type': 'bullet_invader', 'dimension': 10}}

ANGLE = 2
ACTION_INTERVAL = 0.05
DEFAULT_SPEED = 35
DEFAULT_SPEED_BULLETS = 70
MAX_ANGLE = 360
SPEED = 8
MAX_SPEED = 220
STEP_INTERVAL = 1  # 1 second, can be changed to 0.5
UNIT_PROPERTIES = ['x', 'y', 'x1', 'y1', 'angle', 'hits', 'speed', 'id', 'life_count', 'type', 'width', 'height', 'name']


class Unit(object):

    def __init__(self, x, y, angle, hits, speed, type, bullet_type, dimension, controller=None):
        self.controller = controller
        self.type = type
        self.bullet_filename = bullet_type
        self.time_last_calculation = datetime.now()
        self.x = x
        self.y = y
        self.x1 = x
        self.y1 = y
        self.angle = angle
        self.width = dimension
        self.height = dimension
        self.hits = hits
        self.speed = speed
        self.id = str(uuid.uuid4())
        self.is_dead = False
        self.shift = 5
        self.rotate_is_pressing = False
        self.change_speed_is_pressing = False
        self.min_height = int(0 + self.height / 2)
        self.min_width = int(0 + self.width / 2)
        self.max_height = int(self.controller.game_field.get('height', 0) - self.height / 2)
        self.max_width = int(self.controller.game_field.get('width', 0) - self.width / 2)

    def response(self, action, **kwargs):
        if not self.controller:
            return
        data = {action: self.to_dict()}
        data[action].update(kwargs)
        asyncio.async(self.controller.notify_clients(data))

    def to_dict(self):
        result = {}
        for attr in self.__dict__:
            if attr in UNIT_PROPERTIES:
                result[attr] = self.__dict__[attr]
        return result

    def set_in_limit(self, x, y):
        x = x if x > self.min_width else self.min_width
        x = x if x < self.max_width else self.max_width
        y = y if y > self.min_height else self.min_height
        y = y if y < self.max_height else self.max_height
        return x, y

    def compute_new_coordinate(self, interval):
        # Calculate real position
        time_from_last_calculate = (datetime.now() - self.time_last_calculation).total_seconds()
        if time_from_last_calculate < STEP_INTERVAL:
            x = round(self.x + self.speed * time_from_last_calculate * math.sin(round(math.radians(180-self.angle), 2)))
            y = round(self.y + self.speed * time_from_last_calculate * math.cos(round(math.radians(180-self.angle), 2)))
            self.x1, self.y1 = self.set_in_limit(x, y)

        # Calculate future position
        x = round(self.x1 + self.speed * interval * math.sin(round(math.radians(180-self.angle), 2)))
        y = round(self.y1 + self.speed * interval * math.cos(round(math.radians(180-self.angle), 2)))

        self.time_last_calculation = datetime.now()
        if x in range(self.min_width, self.max_width+1) and y in range(self.min_height, self.max_height+1):
            self.move_to(x, y)
        elif self.min_width < self.x1 < self.max_width and self.min_height < self.y1 < self.max_height:
            target_x = x
            target_y = y
            x, y = self.set_in_limit(x, y)
            if x != target_x:
                time_to_crash = math.fabs((x-self.x1) * interval / (target_x - self.x1))
                y = round(self.y1 + self.speed * time_to_crash * math.cos(round(math.radians(180-self.angle), 2)))
            if y != target_y:
                time_to_crash = math.fabs((y-self.y1) * interval / (target_y - self.y1))
                x = round(self.x1 + self.speed * time_to_crash * math.sin(round(math.radians(180-self.angle), 2)))
            if self.__class__.__name__ == 'Hero':
                self.speed = round(math.sqrt((x-self.x1)**2+(y-self.y1)**2)/interval)
            self.move_to(x, y)
            if self.__class__.__name__ != 'Hero':
                asyncio.sleep(time_to_crash)
                self.reset()
        else:
            self.reset()

    def move_to(self, x, y):
        logging.info('Move %s to new coordinate - (%s, %s)' % (self.__class__.__name__, x, y))
        self.x = self.x1
        self.y = self.y1
        self.x1 = x
        self.y1 = y
        self.response('update', frequency=STEP_INTERVAL)

    @asyncio.coroutine
    def rotate(self, side):
        while self.rotate_is_pressing:
            rotate = ANGLE + self.speed * 0.015
            new_angle = self.angle + rotate if side == 'right' else self.angle - rotate
            if new_angle > MAX_ANGLE:
                new_angle -= MAX_ANGLE
            elif new_angle < 0:
                new_angle += MAX_ANGLE
            logging.info('Rotate %s from %s degree to %s degree' % (self.__class__.__name__, self.angle, new_angle))
            self.angle = new_angle
            self.compute_new_coordinate(ACTION_INTERVAL)
            yield from asyncio.sleep(ACTION_INTERVAL)

    def change_speed(self, direct):
        while self.change_speed_is_pressing:
            new_speed = self.speed + SPEED if direct == 'up' else self.speed - SPEED
            self.speed = new_speed > 0 and new_speed or 0
            self.speed = MAX_SPEED if self.speed > MAX_SPEED else self.speed
            logging.info('Change %s speed to %s' % (self.__class__.__name__, self.speed))
            self.compute_new_coordinate(ACTION_INTERVAL)
            yield from asyncio.sleep(ACTION_INTERVAL)

    @asyncio.coroutine
    def notify_collision(self, other_unit, time_interval):
        yield from asyncio.sleep(time_interval)
        if not self.controller.units.get(self.id) or not self.controller.units.get(other_unit.id):
            return
        self.hit(other_unit)
        self.controller.check_if_remove_units([self, other_unit])

    def check_collision(self, other_unit):
        # check if coordinate for two units is the same
        # for this check we also include width and height of unit's image
        # (other_unit.x - other_unit.width / 2 < self.x < other_unit.x + other_unit.width / 2)
        # (other_unit.y - other_unit.height / 2 < self.y < other_unit.y + other_unit.height / 2)
        if self.__class__.__name__ == 'Bullet' and other_unit.__class__.__name__ == 'Bullet':
            return
        if id(self) != id(other_unit) and getattr(self, 'unit_id', '') != id(other_unit) and \
                getattr(other_unit, 'unit_id', '') != id(self):
            A = (self.x, self.y)
            B = (self.x1, self.y1)
            C = (other_unit.x, other_unit.y)
            D = (other_unit.x1, other_unit.y1)
            int_point = object_intersection((A, B), (C, D), round(self.width / 2), round(other_unit.width / 2))
            if int_point:
                if self.x != self.y:
                    A_B_distance = point_distance(A, B)
                    A_P_distance = point_distance(A, int_point)
                else:
                    A_B_distance = point_distance(C, D)
                    A_P_distance = point_distance(C, int_point)
                time_to_point = A_B_distance > 0 and round(STEP_INTERVAL * A_P_distance / A_B_distance, 2) or 0
                if time_to_point < STEP_INTERVAL:
                    asyncio.Task(self.notify_collision(other_unit, time_to_point))
            # if (self.x + self.width / 2 > other_unit.x - other_unit.width / 2) and (self.x - self.width / 2 < other_unit.x + other_unit.width / 2) and \
            #         (self.y + self.height / 2 > other_unit.y - other_unit.height / 2) and (self.y - self.height / 2 < other_unit.y + other_unit.height / 2):
            #     self.hit(other_unit)

    def reset(self):
        raise NotImplementedError

    def hit(self, other_unit):
        raise NotImplementedError

    def kill(self):
        logging.info('Killing - %s ' % self.__class__.__name__)
        self.is_dead = True


class Invader(Unit):

    def __init__(self, x, y, angle, hits=10, speed=DEFAULT_SPEED, type='',
                 bullet_type=UNITS.get('bullet_invader', {}).get('type', ''), dimension=0, controller=None):
        if not type and len(UNITS.get('invader', [])):
            random_number = randint(0, len(UNITS.get('invader', [])) - 1)
            type = UNITS.get('invader', [])[random_number].get('type', '')
            dimension = UNITS.get('invader', [])[random_number].get('dimension', '')
        super(Invader, self).__init__(x, y, angle, hits, speed, type, bullet_type, dimension, controller=controller)

    def reset(self):
        self.angle = randint(0, 360)
        self.compute_new_coordinate(STEP_INTERVAL)
        logging.info('Reset %s angle. New angle - %s' % (self.__class__.__name__, self.angle))

    def hit(self, other_unit):
        unit_class_name = other_unit. __class__.__name__
        logging.info('In hit - %s and %s' % (self.__class__.__name__, unit_class_name))
        if unit_class_name == 'Hero':
            other_unit.hits += 1
            other_unit.decrease_life()
        else:
            if isinstance(other_unit, Bullet):
                self.controller.add_hits(other_unit)
            other_unit.kill()
        self.kill()


class Hero(Unit):

    def __init__(self, x, y, angle, hits=0, speed=0, life_count=3, frequency_fire=0.5, type='',
                 bullet_type=UNITS.get('bullet_hero', {}).get('type', ''), dimension=0, controller=None):
        if not type and len(UNITS.get('hero', [])):
            random_number = randint(0, len(UNITS.get('hero', [])) - 1)
            type = UNITS.get('hero', [])[random_number].get('type', '')
            dimension = UNITS.get('hero', [])[random_number].get('dimension', '')
        super(Hero, self).__init__(x, y, angle, hits, speed, type, bullet_type, dimension, controller=controller)
        self.fire_is_pressing = False
        self.frequency_fire = frequency_fire
        self.last_fire = datetime.now()
        self.life_count = life_count
        self.name = None

    def set_to_new_position(self):
        pos_x = randint(0, self.controller.game_field['width'])
        pos_y = randint(0, self.controller.game_field['height'])
        angle = randint(0, 360)
        self.x = pos_x
        self.y = pos_y
        self.x1 = pos_x
        self.y1 = pos_y
        self.angle = angle
        self.speed = 0
        self.response('update')

    def decrease_life(self):
        if self.life_count > 1:
            self.life_count -= 1
            self.set_to_new_position()
        else:
            self.rotate_is_pressing = False
            self.change_speed_is_pressing = False
            self.fire_is_pressing = False
            self.life_count = 0
            self.kill()
        self.response('update_life')

    @asyncio.coroutine
    def fire(self):
        while self.life_count > 0 and self.fire_is_pressing and \
                        (datetime.now() - self.last_fire).total_seconds() >= self.frequency_fire:
            logging.info('Fire!! Creating bullet!')
            self.compute_new_coordinate(STEP_INTERVAL)
            self.controller.new_unit(Bullet, unit=self, controller=self.controller)
            self.last_fire = datetime.now()
            yield from asyncio.sleep(self.frequency_fire)

    def reset(self):
        self.speed = 0
        self.x = self.x1
        self.y = self.y1
        self.response('update')

    def hit(self, other_unit):
        unit_class_name = other_unit. __class__.__name__
        logging.info('In hit - %s and %s' % (self.__class__.__name__, unit_class_name))
        self.hits += 1
        self.decrease_life()
        if unit_class_name == 'Hero':
            other_unit.hits += 1
            other_unit.decrease_life()
        else:
            if isinstance(other_unit, Bullet):
                self.controller.add_hits(other_unit)
            other_unit.kill()


class Bullet(Unit):
    def __init__(self, unit, controller=None):
        self.unit_id = id(unit)
        dimension = unit.__class__.__name__ == 'Hero' and UNITS.get('bullet_hero', {}).get('dimension', 0)\
            or UNITS.get('bullet_invader', {}).get('dimension', 0)
        super(Bullet, self).__init__(unit.x, unit.y, unit.angle, 0, unit.speed + DEFAULT_SPEED_BULLETS,
                                     unit.bullet_filename, unit.bullet_filename, dimension, controller=controller)

    def reset(self):
        self.kill()
        self.controller.remove_unit(self.id)

    def hit(self, other_unit):
        unit_class_name = other_unit. __class__.__name__
        logging.info('In hit - %s and %s' % (self.__class__.__name__, unit_class_name))
        if unit_class_name == 'Hero':
            self.controller.add_hits(self)
            other_unit.decrease_life()
        elif unit_class_name == 'Invader':
            self.controller.add_hits(self)
            other_unit.kill()
        else:
            other_unit.kill()
        self.kill()


__game = None


def get_game(height=None, width=None, invaders_count=None):
    global __game

    if not __game and height and width and invaders_count is not None:
        __game = GameController(height=height,
                                width=width,
                                invaders_count=invaders_count)
    return __game


class GameController(object):
    _instance = None
    launched = False
    websockets = {}

    def __init__(self, height=None, width=None, invaders_count=None):
        self.game_field = {'height': height, 'width': width}
        self.invaders_count = invaders_count
        self.units = {}
        self.random_type = self.get_unit_type()
        self.set_invaders(self.invaders_count)

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(GameController, cls).__new__(cls)
        return cls._instance

    def action(self, data):
        for key in data:
            action = getattr(self, key)
            hero = self.units.get(data[key].get('id', ''), '')
            if not action and not hero:
                continue
            if key == 'set_name':
                action(hero, data[key].get('name', 'user'))
            else:
                action(hero)

    def new_unit(self, unit_class, *args, **kwargs):
        kwargs['controller'] = self
        unit = unit_class(*args, **kwargs)
        self.units[unit.id] = unit
        unit.response('new')
        unit.compute_new_coordinate(STEP_INTERVAL)
        return unit

    def drop_connection(self, socket):
        socket = self.websockets[id(socket)]
        self.remove_unit(socket['hero'])
        del socket

    @asyncio.coroutine
    def notify_clients(self, data):
        if self.websockets:
            for key in self.websockets:
                if not self.websockets[key]['socket']._closed:
                    self.websockets[key]['socket'].send_str(json.dumps(data))

    def new_hero(self):
        pos_x = randint(0, self.game_field['width'])
        pos_y = randint(0, self.game_field['height'])
        angle = randint(0, 360)
        hero_type = next(self.random_type)
        hero = self.new_unit(Hero, x=pos_x, y=pos_y, angle=angle, type=hero_type['type'],
                             dimension=hero_type['dimension'])
        return hero

    def check_if_remove_units(self, units):
        for unit in units:
            if unit.is_dead:
                self.remove_unit(unit.id)

    def remove_unit(self, id):
        if self.units[id]:
            class_name = self.units[id].__class__.__name__
            self.units[id].response('delete')
            del self.units[id]
            if class_name == 'Invader':
                self.set_invaders(1)

    def start(self, socket, data, *args, **kwargs):
        asyncio.async(self.run())
        my_hero = self.new_hero()
        self.websockets[id(socket)] = {'socket': socket, 'hero': my_hero.id}
        name = data.get('name', 'user')
        self.set_name(my_hero, name)
        start_conditions = {'init': {
            'hero_id': my_hero.id,
            'game': self.game_field,
            'units': self.get_units(),
            'frequency': STEP_INTERVAL}}
        socket.send_str(json.dumps(start_conditions))

    def add_hits(self, bullet):
        for unit in self.units:
            if id(self.units[unit]) == bullet.unit_id and self.units[unit].__class__.__name__ == 'Hero':
                self.units[unit].hits += 1

    @staticmethod
    def get_unit_type():
        i = -1
        types = UNITS['hero'][:]
        shuffle(types)
        while True:
            i += 1
            yield types[i]
            if i == len(types)-1:
                shuffle(types)
                i = -1

    def set_invaders(self, count):
        for count in range(count):
            pos_x = randint(0, self.game_field['width'])
            pos_y = randint(0, self.game_field['height'])
            angle = randint(0, 360)
            speed = randint(30, 70)
            self.new_unit(Invader, x=pos_x, y=pos_y, angle=angle, speed=speed)

    def get_units(self):
        units = []
        if len(self.units):
            units = {unit: self.units[unit].to_dict() for unit in self.units}
        return units

    @staticmethod
    def set_name(hero, name):
        hero.name = name
        hero.compute_new_coordinate(STEP_INTERVAL)

    @staticmethod
    def change_speed_up(hero):
        hero.change_speed_is_pressing = True
        asyncio.async(hero.change_speed('up'))

    @staticmethod
    def change_speed_down(hero):
        hero.change_speed_is_pressing = True
        asyncio.async(hero.change_speed('down'))

    @staticmethod
    def stop_change_speed(hero):
        hero.change_speed_is_pressing = False
        hero.compute_new_coordinate(STEP_INTERVAL)

    @staticmethod
    def start_fire(hero):
        hero.fire_is_pressing = True
        asyncio.async(hero.fire())

    @staticmethod
    def stop_fire(hero):
        hero.fire_is_pressing = False

    @staticmethod
    def rotate_right(hero):
        hero.rotate_is_pressing = True
        asyncio.async(hero.rotate('right'))

    @staticmethod
    def rotate_left(hero):
        hero.rotate_is_pressing = True
        asyncio.async(hero.rotate('left'))

    @staticmethod
    def stop_rotate(hero):
        hero.rotate_is_pressing = False
        hero.compute_new_coordinate(STEP_INTERVAL)

    @asyncio.coroutine
    def run(self):
        if not self.launched:
            self.launched = True
            logging.basicConfig(level=logging.DEBUG)
            logging.info('Starting Space Invaders Game instance.')

            '''this code for moving invaders. Work as a job.
                We set moving_speed for positive - if reach the left coordinate of our game field
                or negative  - if we reach the right coordinate of our game field '''
            while len(self.units) > 0:
                for unit in list(self.units.keys()):
                    if self.units.get(unit):
                        if self.units[unit].speed:
                            self.units[unit].compute_new_coordinate(STEP_INTERVAL)
                        for key in list(self.units.keys()):
                            if self.units.get(unit) and self.units.get(key):
                                self.units[unit].check_collision(self.units[key])
                yield from asyncio.sleep(STEP_INTERVAL)