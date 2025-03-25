import unittest
import bsi

class TestBsiLexer(unittest.TestCase):
    def setUp(self):
        self.lex = bsi.bsi_lexer
        self.data = '''
        ip = "127.0.0.1"
        port = 1337
        '''
        self.tokens = [
            ('KEY', 'ip'),
            ('EQ', '='),
            ('STRING', '"127.0.0.1"'),
            ('KEY', 'port'),
            ('EQ', '='),
            ('NUM', 1337)
        ]

    def test_tokenizer_tokenizes_correctly(self):
        self.lex.input(self.data)

        token_data = [(t.type, t.value) for t in self.lex]

        self.assertEqual(token_data, self.tokens)
