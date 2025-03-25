import unittest
from jvpm import op_codes1


class test_op_codes(unittest.TestCase):

    def test_opcode05(self): #load 2 onto stack
        test_stack = [1, 2]
        test_stack = op_codes1.op_codes.op_code05(test_stack)
        self.assertEqual(test_stack.pop(), 2)

    def test_opcode06(self): #load 3 onto stack
        test_stack = [1, 2]
        test_stack = op_codes1.op_codes.op_code06(test_stack)
        self.assertEqual(test_stack.pop(), 3)

    def test_opcode07(self): #load 4 onto stack
        test_stack = [1, 2]
        test_stack = op_codes1.op_codes.op_code07(test_stack)
        self.assertEqual(test_stack.pop(), 4)

    def test_opcode08(self): #load 5 onto stack
        test_stack = [1, 2]
        test_stack = op_codes1.op_codes.op_code08(test_stack)
        self.assertEqual(test_stack.pop(), 5)

    def test_op_code70(self): # remainder
        test_stack = [1, 2]
        test_stack = op_codes1.op_codes.op_code70(test_stack)
        self.assertEqual(test_stack.pop() , 0)

    def test_op_code78(self): # shift left
        test_stack = [1, 2]
        test_stack = op_codes1.op_codes.op_code78(test_stack)
        self.assertEqual(test_stack.pop() , 4)

    def test_op_code7c(self): #shift right
        test_stack = [1, 2]
        test_stack = op_codes1.op_codes.op_code7c(test_stack)
        self.assertEqual(test_stack.pop() , 1)

    def test_op_code7a(self):  # arithmetic shift right
        test_stack = [2, 15]
        operator = op_codes1.op_codes()
        operator.op_code7a(test_stack)

        self.assertEqual(test_stack.pop(), 3)

    def test_op_code82(self): #bitwise XOR
        test_stack = [1, 2]
        test_stack = op_codes1.op_codes.op_code82(test_stack)
        self.assertEqual(test_stack.pop() , 3)

    def test_op_code80(self): # bitwise OR
        test_stack = [1, 2]
        test_stack = op_codes1.op_codes.op_code80(test_stack)
        self.assertEqual(test_stack.pop() , 3)


    def test_op_code60(self): # add
        test_stack = [1, 2, 2147483647, 2147483647, -2147483647, -2147483647]
        test_stack = op_codes1.op_codes.op_code60(test_stack)
        self.assertEqual(test_stack.pop(), -2147483647)
        test_stack = op_codes1.op_codes.op_code60(test_stack)
        self.assertEqual(test_stack.pop(), 2147483647)
        test_stack = op_codes1.op_codes.op_code60(test_stack)
        self.assertEqual(test_stack.pop(), 3)

    def test_op_code_64(self):  # subtract
        test_stack = [2, 3]
        operator = op_codes1.op_codes()
        operator.op_code64(test_stack)

        self.assertEqual(test_stack.pop(), 1)

    def test_op_code7e(self): # bitwise AND
        test_stack = [1, 2]
        test_stack = op_codes1.op_codes.op_code7e(test_stack)
        self.assertEqual(test_stack.pop(), 1&2)

    def test_op_code6c(self): # integer division
        test_stack = [1, 2, 2, 0]
        self.assertRaises(ArithmeticError, test_stack = op_codes1.op_codes.op_code6c(test_stack))
        test_stack = op_codes1.op_codes.op_code6c(test_stack)
        self.assertEqual(test_stack.pop(), 1 // 2)

    def test_op_code68(self): # multiplication
        test_stack = [1, 2, 2147483647, 2147483647, 2147483647, 4, 2147483647, 5, -2147483647, -2147483647, -2147483647, 4, -2147483647, 5]
        test_stack = op_codes1.op_codes.op_code68(test_stack)
        self.assertEqual(test_stack.pop(), -2147483647)
        test_stack = op_codes1.op_codes.op_code68(test_stack)
        self.assertEqual(test_stack.pop(), 0)
        test_stack = op_codes1.op_codes.op_code68(test_stack)
        self.assertEqual(test_stack.pop(), 0)
        test_stack = op_codes1.op_codes.op_code68(test_stack)
        self.assertEqual(test_stack.pop(), 2147483643)
        test_stack = op_codes1.op_codes.op_code68(test_stack)
        self.assertEqual(test_stack.pop(), -4)
        test_stack = op_codes1.op_codes.op_code68(test_stack)
        self.assertEqual(test_stack.pop(), 1)
        test_stack = op_codes1.op_codes.op_code68(test_stack)
        self.assertEqual(test_stack.pop(), 1 * 2)

    def test_op_code74(self): # negative
        test_stack = [1, 2]
        test_stack = op_codes1.op_codes.op_code74(test_stack)
        self.assertEqual(test_stack.pop() , -1 * 2)

    def test_opcode02(self): #load -1 onto stack
        test_stack = [1, 2]
        test_stack = op_codes1.op_codes.op_code02(test_stack)
        self.assertEqual(test_stack.pop(), -1)

    def test_opcode03(self): #load 0 onto stack
        test_stack = [1, 2]
        test_stack = op_codes1.op_codes.op_code03(test_stack)
        self.assertEqual(test_stack.pop(), 0)

    def test_opcode04(self): #load 1 onto stack
        test_stack = []
        test_stack = op_codes1.op_codes.op_code04(test_stack)
        self.assertEqual(test_stack.pop(), 1)

    #def test_opcode91(self): #convert int to byte
    #    test_stack = [1, 2, 2147483647, -214748367, 500, -500, 256, -256, 768, 770]
    #    test_stack = op_codes1.op_codes.op_code91(test_stack)
    #    self.assertEqual(test_stack.pop(), bytes([254]))
    #    test_stack = op_codes1.op_codes.op_code91(test_stack)
    #    self.assertEqual(test_stack.pop(), bytes([0]))
    #    test_stack = op_codes1.op_codes.op_code91(test_stack)
    #    self.assertEqual(test_stack.pop(), bytes([0]))
    #    test_stack = op_codes1.op_codes.op_code91(test_stack)
    #    self.assertEqual(test_stack.pop(), bytes([0]))
    #    test_stack = op_codes1.op_codes.op_code91(test_stack)
    #    self.assertEqual(test_stack.pop(), bytes([12]))
    #    test_stack = op_codes1.op_codes.op_code91(test_stack)
    #    self.assertEqual(test_stack.pop(), bytearray([256-12]))
    #    test_stack = op_codes1.op_codes.op_code91(test_stack)
    #    self.assertEqual(test_stack.pop(), bytes([0]))
    #    test_stack = op_codes1.op_codes.op_code91(test_stack)
    #    self.assertEqual(test_stack.pop(), bytes([-1]))
    #    test_stack = op_codes1.op_codes.op_code91(test_stack)
    #    self.assertEqual(test_stack.pop(), bytes([2]))
    #    test_stack = op_codes1.op_codes.op_code91(test_stack)
    #    self.assertEqual(test_stack.pop(), bytes([1]))

    def test_opcode92(self):
        test_stack = [-100, 65, 75, 90, 97, 100, 122]
        test_stack = op_codes1.op_codes.op_code92(test_stack)
        self.assertEqual(test_stack.pop(), 'z')
        test_stack = op_codes1.op_codes.op_code92(test_stack)
        self.assertEqual(test_stack.pop(), 'd')
        test_stack = op_codes1.op_codes.op_code92(test_stack)
        self.assertEqual(test_stack.pop(), 'a')
        test_stack = op_codes1.op_codes.op_code92(test_stack)
        self.assertEqual(test_stack.pop(), 'Z')
        test_stack = op_codes1.op_codes.op_code92(test_stack)
        self.assertEqual(test_stack.pop(), 'K')
        test_stack = op_codes1.op_codes.op_code92(test_stack)
        self.assertEqual(test_stack.pop(), 'A')
        test_stack = op_codes1.op_codes.op_code92(test_stack)
        self.assertEqual(test_stack.pop(), '?')

    def test_opcode87(self):
        test_stack = [-100, 65, 75, 90]
        test_stack = op_codes1.op_codes.op_code87(test_stack)
        self.assertEqual(test_stack.pop(), 90.0)
        test_stack = op_codes1.op_codes.op_code87(test_stack)
        self.assertEqual(test_stack.pop(), 75.0)
        test_stack = op_codes1.op_codes.op_code87(test_stack)
        self.assertEqual(test_stack.pop(), 65.0)
        test_stack = op_codes1.op_codes.op_code87(test_stack)
        self.assertEqual(test_stack.pop(), -100.0)

    def test_opcode86(self):
        test_stack = [-100, 65, 75, 90]
        test_stack = op_codes1.op_codes.op_code86(test_stack)
        self.assertEqual(test_stack.pop(), 90.0)
        test_stack = op_codes1.op_codes.op_code86(test_stack)
        self.assertEqual(test_stack.pop(), 75.0)
        test_stack = op_codes1.op_codes.op_code86(test_stack)
        self.assertEqual(test_stack.pop(), 65.0)
        test_stack = op_codes1.op_codes.op_code86(test_stack)
        self.assertEqual(test_stack.pop(), -100.0)

    def test_opcode85(self):
        test_stack = [2147483647, -2147483647]
        test_stack = op_codes1.op_codes.op_code85(test_stack)
        self.assertEqual(test_stack.pop(), -2147483647)
        test_stack = op_codes1.op_codes.op_code85(test_stack)
        self.assertEqual(test_stack.pop(), 2147483647)

    def test_opcode1a(self):
        test_stack = []
        test_localvar = [20]
        test_stack = op_codes1.op_codes.op_code1a(test_stack, test_localvar)
        self.assertEqual(test_stack.pop(), 20)

    def test_opcode1b(self):
        test_stack = []
        test_localvar = [20, 10]
        test_stack = op_codes1.op_codes.op_code1b(test_stack, test_localvar)
        self.assertEqual(test_stack.pop(), 10)

    def test_opcode1c(self):
        test_stack = []
        test_localvar = [20, 10, 5]
        test_stack = op_codes1.op_codes.op_code1c(test_stack, test_localvar)
        self.assertEqual(test_stack.pop(), 5)

    def test_opcode1d(self):
        test_stack = []
        test_localvar = [20, 5, 8, 9]
        test_stack = op_codes1.op_codes.op_code1d(test_stack, test_localvar)
        self.assertEqual(test_stack.pop(), 9)

    def test_opcode15(self):
        test_stack = []
        test_localvar = [20, 5, 8, 9]
        test_stack = op_codes1.op_codes.op_code15(test_stack, test_localvar, 2)
        self.assertEqual(test_stack.pop(), 8)
        test_stack = op_codes1.op_codes.op_code15(test_stack, test_localvar, 0)
        self.assertEqual(test_stack.pop(), 20)

    def test_opcode93(self):
        test_stack = [2147483647, -2147483647, 32768, -32770]
        test_stack = op_codes1.op_codes.op_code93(test_stack)
        self.assertEqual(test_stack.pop(), 32766)
        test_stack = op_codes1.op_codes.op_code93(test_stack)
        self.assertEqual(test_stack.pop(), -32768)
        test_stack = op_codes1.op_codes.op_code93(test_stack)
        self.assertEqual(test_stack.pop(), 0)
        test_stack = op_codes1.op_codes.op_code93(test_stack)
        self.assertEqual(test_stack.pop(), -1)

    def test_opcode2e(self):
        test_stack = []
        test_array = [2147483647, -2147483647, 32768, -32770]
        index = 2
        test_stack = op_codes1.op_codes.op_code2e(test_array, index)
        self.assertEqual(test_stack.pop(), 32768)

    #def test_opcode61(self):
    #
        test_stack = []


    def test_long_builder(self):
        hexstr = "7FFFFFFFFFFFFFFE"
        self.assertEqual(op_codes1.op_codes.long_builder(hexstr), 9223372036854775806)

    def test_opcode16(self):
        hexstr = "7FFFFFFFFFFFFFFF"
        self.assertEqual(op_codes1.op_codes.op_code16(hexstr).pop(), 9223372036854775807)

    def test_opcode1e(self):
        test_local_vars = ["7FFFFFFFFFFFFFFF", "7FFFFFFFFFFFFFFF", "7FFFFFFFFFFFFFFF", "7FFFFFFFFFFFFFFF"]
        test_stack = []
        test_stack = op_codes1.op_codes.op_code1e(test_stack, test_local_vars)
        self.assertEqual(test_stack.pop(), 9223372036854775807)

    def test_opcode1f(self):
        test_local_vars = ["7FFFFFFFFFFFFFFF", "07FFFFFFFFFFFFFF", "7FFFFFFFFFFFFFFF", "7FFFFFFFFFFFFFFF"]
        test_stack = []
        test_stack = op_codes1.op_codes.op_code1f(test_stack, test_local_vars)
        self.assertEqual(test_stack.pop(), 576460752303423487)

    def test_opcode20(self):
        test_local_vars = ["7FFFFFFFFFFFFFFF", "7FFFFFFFFFFFFFFF", "007FFFFFFFFFFFFF", "7FFFFFFFFFFFFFFF"]
        test_stack = []
        test_stack = op_codes1.op_codes.op_code20(test_stack, test_local_vars)
        self.assertEqual(test_stack.pop(), 36028797018963967)

    def test_opcode21(self):
        test_local_vars = ["7FFFFFFFFFFFFFFF", "7FFFFFFFFFFFFFFF", "7FFFFFFFFFFFFFFF", "007FFFFFFFFFFFFF"]
        test_stack = []
        test_stack = op_codes1.op_codes.op_code21(test_stack, test_local_vars)
        self.assertEqual(test_stack.pop(), 36028797018963967)
        
    def test_opcode61(self):
        test_stack = [9223372036854775807, 1, -9223372036854775808, -1, 9223372036854775807, 10, -10, -9223372036854775808, 10, 20]
        test_stack = op_codes1.op_codes.op_code61(test_stack)
        self.assertEqual(test_stack.pop(), 30)
        test_stack = op_codes1.op_codes.op_code61(test_stack)
        self.assertEqual(test_stack.pop(), 9223372036854775797)
        test_stack = op_codes1.op_codes.op_code61(test_stack)
        self.assertEqual(test_stack.pop(), -9223372036854775799)
        test_stack = op_codes1.op_codes.op_code61(test_stack)
        self.assertEqual(test_stack.pop(),9223372036854775806)
        test_stack = op_codes1.op_codes.op_code61(test_stack)
        self.assertEqual(test_stack.pop(), -9223372036854775808)
        
    def test_opcode6d(self):
        test_stack = [9223372036854775807, 9223372036854775807, 9223372036854775807, 5, -9223372036854775808, 5, -9223372036854775808, -5]
        test_stack = op_codes1.op_codes.op_code6d(test_stack)
        self.assertEqual(test_stack.pop(), 1844674407370955161)
        test_stack = op_codes1.op_codes.op_code6d(test_stack)
        self.assertEqual(test_stack.pop(), -1844674407370955162)
        test_stack = op_codes1.op_codes.op_code6d(test_stack)
        self.assertEqual(test_stack.pop(), 1844674407370955161)
        test_stack = op_codes1.op_codes.op_code6d(test_stack)
        self.assertEqual(test_stack.pop(), 1)
        
    def test_opcode75(self):
        test_stack = [-9223372036854775808, 9223372036854775807]
        test_stack = op_codes1.op_codes.op_code75(test_stack)
        self.assertEqual(test_stack.pop(), -9223372036854775807)
        test_stack = op_codes1.op_codes.op_code75(test_stack)
        self.assertEqual(test_stack.pop(), -9223372036854775808)
        
    def test_opcode94(self):
        test_stack = [9223372036854775807, 9223372036854775807, 9223372036854775807, 5, -9223372036854775808, 5, -9223372036854775808, -5]
        test_stack = op_codes1.op_codes.op_code94(test_stack)
        self.assertEqual(test_stack.pop(), -1)
        test_stack = op_codes1.op_codes.op_code94(test_stack)
        self.assertEqual(test_stack.pop(), -1)
        test_stack = op_codes1.op_codes.op_code94(test_stack)
        self.assertEqual(test_stack.pop(), 1)
        test_stack = op_codes1.op_codes.op_code94(test_stack)
        self.assertEqual(test_stack.pop(), 0)
        
        