from unittest import TestCase

from unicore.hub.service import utils


class UtilsTestCase(TestCase):

    def test_make_password(self):
        for l in range(1, 20):
            password = utils.make_password(bit_length=l)
            self.assertTrue(len(password) > l)
