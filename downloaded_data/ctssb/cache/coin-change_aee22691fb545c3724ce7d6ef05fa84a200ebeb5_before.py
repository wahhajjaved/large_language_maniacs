from mcdonalds import McDonalds
import unittest

class McDonaldsTest(unittest.TestCase):

	def test_change_for_zero(self):
		mcdonalds = McDonalds((6,9,20))
		self.assertTrue(mcdonalds.is_changeable(6))
		self.assertTrue(mcdonalds.is_changeable(20))
		self.assertTrue(mcdonalds.is_changeable(9))
		self.assertTrue(mcdonalds.is_changeable(18))
		self.assertTrue(mcdonalds.is_changeable(15))
		self.assertTrue(mcdonalds.is_changeable(0))

		self.assertFalse(mcdonalds.is_changeable(1))
		self.assertFalse(mcdonalds.is_changeable(8))
		self.assertFalse(mcdonalds.is_changeable(17))
