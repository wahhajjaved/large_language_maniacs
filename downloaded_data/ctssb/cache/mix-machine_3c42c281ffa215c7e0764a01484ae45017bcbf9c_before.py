# test_memory.py

# module for testing class Memory and functions mix2dec, dec2mix

import unittest, sys, os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from operations import *

class OperationsTestCase(unittest.TestCase):
  def test_get_codes(self):
    """ Test some codes """
    self.assertEqual(get_codes('NOP'), (0,0))
    self.assertEqual(get_codes('LDA'), (8,5))
    self.assertEqual(get_codes('JNOV'), (39,3))
    self.assertEqual(get_codes('CMPX'), (63,5))

    self.assertEqual(get_codes('BLAH'), (None,5))

  def test_is_valid_operation(self):
    for op in "LDA CMPX JAN ent4 cmpA EQU ORIG END CON ALF".split():
      self.assertTrue(is_valid_operation(op))
    
    for op in "BLAH QQQ".split():
      self.assertFalse(is_valid_operation(op))

  def test_is_instruction(self):
    for op in "LDA CMPX JAN ent4 cmpA".split():
      self.assertTrue(is_instruction(op))
    
    for op in " EQU ORIG END CON ALF BLAH QQQ".split():
      self.assertFalse(is_instruction(op))

  def test_arg_required(self):
    for op in " Equ orig enD CON".split():
      self.assertTrue(is_arg_required(op))
    
    for op in " STA NOP ALF BLAH QQQ".split():
      self.assertFalse(is_arg_required(op))

suite = unittest.makeSuite(OperationsTestCase, 'test')

if __name__ == "__main__":
	unittest.main()

