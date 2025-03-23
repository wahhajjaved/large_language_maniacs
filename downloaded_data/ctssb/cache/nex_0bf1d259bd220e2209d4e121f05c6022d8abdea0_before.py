import logging
import ply.yacc as yacc

from process import CatCode, MathClass, MathCode, GlyphCode, DelimiterCode
from lexer import PLYLexer, tokens, LexMode

logger = logging.getLogger(__name__)
logger.setLevel('DEBUG')


class DigitCollection(object):

    def __init__(self, base):
        self.base = base
        self.digits = []


def is_control_sequence(value):
    return isinstance(value, dict) and value['type'] == 'control_sequence'


def is_backtick(value):
    return isinstance(value, dict) and value['type'] == 'backtick'


def evaluate(value):
    if is_backtick(value):
        unexpanded_token = value['token']
        if unexpanded_token['type'] == 'control_sequence':
            expanded_tokens = evaluate(value['token'])
            # Check the target token expands to just one token.
            assert len(expanded_tokens) == 1
            expanded_token = expanded_tokens[0]
            # Check the single token is one character.
            assert len(expanded_token) == 1
        elif unexpanded_token['type'] == 'character':
            expanded_token = unexpanded_token['char']
        return ord(expanded_token)
    if is_control_sequence(value):
        name = value['name']
        value = lexer.state.control_sequences[name]
    return value


precedence = (
    ('left', 'SPACE'),
    ('left', 'CONTROL_SEQUENCE'),
)


def p_commands_extend(p):
    '''
    commands : commands command
    '''
    p[0] = p[1]
    p[0].append(p[2])


def p_commands(p):
    '''
    commands : command
    '''
    p[0] = [p[1]]


def p_command(p):
    '''
    command : macro_assignment
            | control_sequence
            | character
            | simple_assignment
            | PAR
            | SPACE
            | message
    '''
    p[0] = p[1]


def p_message(p):
    '''
    message : MESSAGE general_text
    '''
    p[0] = {'type': 'message', 'content': p[2]}


def p_general_text(p):
    '''
    general_text : filler implicit_left_brace seen_def_cs_name BALANCED_TEXT
    '''
    p[0] = p[3]


def p_filler(p):
    '''
    filler : optional_spaces
           | filler RELAX optional_spaces
    '''
    pass


def p_implicit_left_brace(p):
    '''
    implicit_left_brace : LEFT_BRACE
    '''
    p[0] = p[1]


def p_macro_assignment_prefix(p):
    '''
    macro_assignment : PREFIX macro_assignment
    '''
    p[0] = p[2]
    p[0]['prefix'] = p[1]['name']


def p_macro_assignment(p):
    '''
    macro_assignment : definition
    '''
    p[0] = p[1]
    lexer.state.control_sequences[p[1]['name']] = p[1]['content']
    lexer.lex_mode = LexMode.expand


def p_definition(p):
    '''
    definition : DEF control_sequence seen_def_cs_name definition_text
    '''
    p[0] = {'type': 'definition', 'name': p[2]['name'], 'content': p[4]}


def p_seen_def_cs_name(p):
    '''
    seen_def_cs_name :
    '''
    lexer.lex_mode = LexMode.read_balanced_text


def p_definition_text(p):
    '''
    definition_text : LEFT_BRACE BALANCED_TEXT
    '''
    p[0] = p[2]


def p_character(p):
    '''
    character : CHARACTER
              | EQUALS
              | PLUS_SIGN
              | MINUS_SIGN
              | ZERO
              | ONE
              | TWO
              | THREE
              | FOUR
              | FIVE
              | SIX
              | SEVEN
              | EIGHT
              | NINE
              | A
              | B
              | C
              | D
              | E
              | F
              | SINGLE_QUOTE
              | DOUBLE_QUOTE
              | BACKTICK
    '''
    p[0] = {'type': 'character', 'char': p[1]['char'], 'cat': p[1]['cat']}


def p_control_sequence(p):
    '''
    control_sequence : CONTROL_SEQUENCE
                     | SINGLE_CHAR_CONTROL_SEQUENCE
    '''
    p[0] = p[1]


def p_control_sequence_active(p):
    '''
    control_sequence : ACTIVE_CHARACTER
    '''
    # We will prefix active characters with @.
    # This really needs changing, but will do for now.
    p[0] = {'name': '@' + p[1]['char'], 'type': 'control_sequence'}


def p_simple_assignment(p):
    '''
    simple_assignment : short_hand_definition
                      | code_assignment
                      | variable_assignment
    '''
    p[0] = p[1]


def p_variable_assignment(p):
    '''
    variable_assignment : integer_variable equals number
    '''
    p[0] = {'type': 'variable_assignment', 'variable': p[1], 'value': p[3]}


def p_integer_variable_count(p):
    '''
    integer_variable : COUNT number
    '''
    p[0] = {'type': 'count', 'register': p[2]}


def p_integer_variable_count_def(p):
    '''
    integer_variable : COUNT_DEF_TOKEN
    '''
    p[0] = {'type': 'count', 'register': p[1]}


def p_short_hand_definition(p):
    '''
    short_hand_definition : short_hand_def control_sequence equals number
    '''
    code = evaluate(p[4]['size'])
    def_type = p[1]['def_type']

    state_token_type = '{}_token'.format(def_type)
    state_token = {'type': state_token_type, 'value': code}
    control_sequence_name = p[2]['name']
    lexer.state.control_sequences[control_sequence_name] = [state_token]

    p[0] = {'type': def_type, 'name': control_sequence_name, 'code': code}


def p_short_hand_def(p):
    '''
    short_hand_def : CHAR_DEF
                   | MATH_CHAR_DEF
                   | COUNT_DEF
    '''
    p[0] = {'type': 'short_hand_def', 'def_type': p[1]['name']}


def split_at(s, inds):
    inds = [0] + list(inds) + [len(s)]
    return [s[inds[i]:inds[i + 1]] for i in range(0, len(inds) - 1)]


def split_hex_code(n, hex_length, inds):
    # Get the zero-padded string representation of the number in base 16.
    n_hex = format(n, '0{}x'.format(hex_length))
    # Check the number is of the correct magnitude.
    assert len(n_hex) == hex_length
    # Split the hex string into pieces, at the given indices.
    parts_hex = split_at(n_hex, inds)
    # Convert each part from hex to decimal.
    parts = [int(part, base=16) for part in parts_hex]
    return parts


def p_code_assignment(p):
    '''
    code_assignment : code_name number equals number
    '''
    code_type, char_num, code = p[1]['code_type'], p[2], p[4]
    char_num, code_num = evaluate(char_num['size']), evaluate(code['size'])
    char = chr(char_num)
    code_type_to_char_map = {
        'catcode': lexer.state.char_to_cat,
        'mathcode': lexer.state.char_to_math_code,
        'uccode': lexer.state.upper_case_code,
        'lccode': lexer.state.lower_case_code,
        'sfcode': lexer.state.space_factor_code,
        'delcode': lexer.state.delimiter_code,
    }
    if code_type == 'catcode':
        code = CatCode(code_num)
    elif code_type == 'mathcode':
        parts = split_hex_code(code_num, hex_length=4, inds=(1, 2))
        math_class_i, family, position = parts
        math_class = MathClass(math_class_i)
        glyph_code = GlyphCode(family, position)
        code = MathCode(math_class, glyph_code)
    elif code_type in ('uccode', 'lccode'):
        code = chr(code_num)
    elif code_type == 'sfcode':
        code = code_num
    elif code_type == 'delcode':
        parts = split_hex_code(code_num, hex_length=6, inds=(1, 3, 4))
        small_family, small_position, large_family, large_position = parts
        small_glyph_code = GlyphCode(small_family, small_position)
        large_glyph_code = GlyphCode(large_family, large_position)
        code = DelimiterCode(small_glyph_code, large_glyph_code)
    char_map = code_type_to_char_map[code_type]
    char_map[char] = code
    p[0] = {'type': 'code_assignment', 'code_type': code_type,
            'char': char, 'code': code}


def p_code_name(p):
    '''
    code_name : CAT_CODE
              | MATH_CODE
              | UPPER_CASE_CODE
              | LOWER_CASE_CODE
              | SPACE_FACTOR_CODE
              | DELIMITER_CODE
    '''
    p[0] = {'type': 'code_name', 'code_type': p[1]['name']}


def p_number(p):
    '''
    number : optional_signs unsigned_number
    '''
    p[0] = {'sign': p[1], 'size': p[2]}


def p_unsigned_number(p):
    '''
    unsigned_number : normal_integer
    '''
    # | coerced_integer
    p[0] = p[1]


def get_constant(constant):
    return int(constant['digits'], base=constant['base'])


def p_normal_integer_internal_integer(p):
    '''
    normal_integer : internal_integer
    '''
    p[0] = p[1]


def p_internal_integer(p):
    '''
    internal_integer : CHAR_DEF_TOKEN
                     | MATH_CHAR_DEF_TOKEN
                     | COUNT_DEF_TOKEN
    '''
    # TODO: add other kinds of internal integer.
    p[0] = p[1]


def p_normal_integer_integer(p):
    '''
    normal_integer : integer_constant one_optional_space
    '''
    p[0] = get_constant(p[1])


def p_normal_integer_weird_base(p):
    '''
    normal_integer : SINGLE_QUOTE octal_constant one_optional_space
                   | DOUBLE_QUOTE hexadecimal_constant one_optional_space
    '''
    p[0] = get_constant(p[2])


def p_normal_integer_character(p):
    '''
    normal_integer : BACKTICK character_token one_optional_space
    '''
    p[0] = {'type': 'backtick', 'token': p[2]}


def p_character_token(p):
    '''
    character_token : SINGLE_CHAR_CONTROL_SEQUENCE
                    | character
    '''
    # TODO: make this possible.
    '''
                    | active character
    '''
    p[0] = p[1]


def process_digits(p, base):
    new_digit = p[1]['char']
    if len(p) > 2:
        constant = p[2]
        # We work right-to-left, so the new digit should be added on the left.
        constant['digits'] = new_digit + constant['digits']
    else:
        constant = {
            'base': base,
            'digits': new_digit
        }
    return constant


def p_hexadecimal_constant(p):
    '''
    hexadecimal_constant : hexadecimal_digit
                         | hexadecimal_digit hexadecimal_constant
    '''
    p[0] = process_digits(p, base=16)


def p_integer_constant(p):
    '''
    integer_constant : digit
                     | digit integer_constant
    '''
    p[0] = process_digits(p, base=10)


def p_octal_constant(p):
    '''
    octal_constant : octal_digit
                   | octal_digit octal_constant
    '''
    p[0] = process_digits(p, base=8)


def p_hexadecimal_digit(p):
    '''
    hexadecimal_digit : digit
                      | A
                      | B
                      | C
                      | D
                      | E
                      | F
    '''
    p[0] = p[1]


def p_digit(p):
    '''
    digit : octal_digit
          | EIGHT
          | NINE
    '''
    p[0] = p[1]


def p_octal_digit(p):
    '''
    octal_digit : ZERO
                | ONE
                | TWO
                | THREE
                | FOUR
                | FIVE
                | SIX
                | SEVEN
    '''
    p[0] = p[1]


def p_one_optional_space(p):
    '''
    one_optional_space : SPACE
                       | empty
    '''
    pass


def p_optional_signs(p):
    '''
    optional_signs : optional_spaces
                   | optional_signs plus_or_minus optional_spaces
    '''
    flip_sign = lambda s: '+' if s == '-' else '-'
    if len(p) > 2:
        p[0] = p[2]
        if p[1] == '-':
            p[0] = flip_sign(p[0])
    else:
        p[0] = '+'


def p_plus_or_minus(p):
    '''
    plus_or_minus : PLUS_SIGN
                  | MINUS_SIGN
    '''
    p[0] = p[1]['char']


def p_equals(p):
    '''
    equals : optional_spaces
           | optional_spaces EQUALS
    '''
    pass


def p_optional_spaces(p):
    '''
    optional_spaces : empty
                    | SPACE optional_spaces
    '''
    pass


def p_empty(p):
    '''
    empty :
    '''
    pass


# Error rule for syntax errors
def p_error(p):
    import pdb; pdb.set_trace()
    print("Syntax error in input!")

# Build the parser
parser = yacc.yacc(debug=True)
lexer = PLYLexer()
