import unittest

class TestFizzBuzz(unittest.TestCase):

	def test_3_donne_fizz(self):
		self.assertEqual("Fizz", fizz_buzz(3))
	def test_5_donne_buzz(self):
		self.assertEqual("Buzz", fizz_buzz(3))
	def fizz_buzz(chiffre):
		return "Fizz"

if __name__ == '__main__':
	unittest.main()
 