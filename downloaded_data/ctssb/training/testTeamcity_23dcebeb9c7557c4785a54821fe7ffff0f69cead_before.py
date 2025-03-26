import unittest


class DesTests(unittest.TestCase):
    def test(self):
        self.assertTrue(True)

    def autreTest(self):
        self.assertEquals(3, 4)


if __name__ == '__main__':
    unittest.main()