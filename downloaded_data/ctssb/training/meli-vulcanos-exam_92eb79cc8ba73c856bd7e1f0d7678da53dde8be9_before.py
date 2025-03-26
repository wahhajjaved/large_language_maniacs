import unittest

from model.geometry import Polar
from model.planet import Planet


class AntiClockwisePlanetTest(unittest.TestCase):

    def setUp(self):
        self.planet_radio = 100
        self.test_planet = Planet("earth", coor=Polar(self.planet_radio, 0), angular_velocity=1)

    def test_creation(self):
        coor = self.test_planet.coor
        cart = coor.to_cartesian()
        self.assertEqual(cart.x, 100)
        self.assertEqual(cart.y, 0)
        self.assertEqual(coor.degrees, 0)
        self.assertEqual(coor.radians, 0)

    def test_time_enlapsed(self):
        # to 45 days or 45 degrees or pi/4
        self.test_planet.grownup(45)
        current = self.test_planet.coor
        expected = Polar(self.planet_radio, 45)
        self.assertEqual(current, expected)


        # to 45 days more or 90 degrees or pi/2
        self.test_planet.grownup(45)
        current = self.test_planet.coor
        expected = Polar(self.planet_radio, 90)
        self.assertEqual(current, expected)

        # to 360 days more or 45 degrees or pi/2
        self.test_planet.grownup(360)
        current = self.test_planet.coor
        expected = Polar(self.planet_radio, 90)
        self.assertEqual(current, expected)


class ClockwisePlanetTest(unittest.TestCase):

    def setUp(self):
        self.planet_radio = 200
        self.test_planet = Planet("earth", coor=Polar(self.planet_radio, 0), angular_velocity=-2)

    def test_creation(self):
        coor = self.test_planet.coor
        cart = coor.to_cartesian()
        self.assertEqual(cart.x, 200)
        self.assertEqual(cart.y, 0)
        self.assertEqual(coor.degrees, 0)
        self.assertEqual(coor.radians, 0)

    def test_time_enlapsed(self):
        # to 45 days or 270 degrees
        self.test_planet.grownup(45)
        current = self.test_planet.coor
        expected = Polar(self.planet_radio, 270)
        self.assertEqual(current, expected)

        # to 45 days more or 180 degrees
        self.test_planet.grownup(45)
        current = self.test_planet.coor
        expected = Polar(self.planet_radio, 180)
        self.assertEqual(current, expected)

        # to 360 days more or 180 degrees
        self.test_planet.grownup(360)
        current = self.test_planet.coor
        expected = Polar(self.planet_radio, 180)
        self.assertEqual(current, expected)

