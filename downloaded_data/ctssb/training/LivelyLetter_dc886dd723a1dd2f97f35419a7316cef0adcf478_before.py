from mock import Mock
from os.path import dirname, join
import unittest

from LivelyLetter import Letter

THIS_DIR = dirname(__file__)


class TestConditional(unittest.TestCase):

    def setUp(self):
        with open(join(THIS_DIR, "cond_method_letter.txt"), "r") as f:
            self.text = f.read().strip()
        super(TestConditional, self).setUp()

    def tearDown(self):
        super(TestConditional, self).tearDown()

    def test_conditional_true(self):
        expected = "Jane, I like how you mentioned widgets. [[# discussion#is_long #]]|{You spent a lot of time on it!}"
        discussion = Mock()
        discussion.is_long = True
        ltr_obj = Letter(text=self.text)
        actual = ltr_obj.apply_conds({
            'discussion': discussion,
        })
        self.assertEqual(expected, actual)

    def test_conditional_false(self):
        expected = "Jane, I like how you mentioned widgets."
        discussion = Mock()
        discussion.is_long = False
        ltr_obj = Letter(text=self.text)
        actual = ltr_obj.apply_conds({
            'discussion': discussion,
        })
        self.assertEqual(expected, actual)

if __name__ == '__main__':
    unittest.main()


