import unittest


class DesTests(unittest.TestCase):
    def test(self):
        self.assertTrue(True)

    def autreTest(self):
        self.assertEquals(3, 3)


if __name__ == '__main__':
    unittest.main()