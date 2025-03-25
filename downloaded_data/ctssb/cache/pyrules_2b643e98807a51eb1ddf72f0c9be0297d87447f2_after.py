import unittest
from pyrules2 import RuleBook, rule, when, anything, place,  Driving, RESET, reroute, limit


BASE = place('Erslev, Denmark', milk=RESET)
LARS = place('Snedsted, Denmark', milk=18)
TINA = place('Bedsted Thy, Denmark', milk=20)
LISA = place('Redsted, Denmark', milk=10)
KARL = place('Rakkeby, Denmark', milk=6)
ROUNDTRIP = Driving.route(BASE, LARS, TINA, BASE, LISA, KARL, BASE)


class Dairy(RuleBook):
    @rule
    def roundtrip(self, rt=anything):
        return when(rt=ROUNDTRIP) | reroute(self.roundtrip(rt))

    @rule
    def viable(self, rt=anything):
        return limit(milk=30)(self.roundtrip(rt))


class Test(unittest.TestCase):
    def test_balance(self):
        d = Dairy()
        for scenario in d.viable():
            rt = scenario['rt']
            self.assertIn(rt.milk, [28, 30])
            self.assertLess(370000, rt.distance)
            self.assertLess(rt.distance, 382000)
            self.assertLess(5*3600, rt.duration)
            self.assertLess(rt.duration, 6*3600)
        self.assertEqual(16, len(list(d.viable())))


if __name__ == "__main__":
    unittest.main()
