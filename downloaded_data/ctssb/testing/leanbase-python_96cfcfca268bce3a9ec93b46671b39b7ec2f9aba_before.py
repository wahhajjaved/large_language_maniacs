import typing
import math
import enum
import re

class Kinds(enum.Enum):
    NUMERIC = 'numeric'
    BOOLEAN = 'boolean'
    DATE    = 'date'
    STRING  = 'string'

class Operators(enum.Enum):
    GTE = 'Greater than or equal to'
    LTE = 'Lesser than or equal to'
    GT  = 'Greater than'
    LT  = 'Lesser than'

    IS  = 'Is'
    ISNOT = 'Is not'

    EQUALS = 'Equals'
    DNEQUAL = 'Does not equal'

    STRTWITH = 'Starts with'
    ENDSWITH = 'Ends with'
    MATCHES  = 'Matches (regex)'
    CONTAINS  = 'Contains'

TRUISH = ('True', 'true', '1', 'yes', 'Yes')
FLOAT_TOLERANCE = 10e-4

O = Operators

OperatorMapping = {
    Kinds.NUMERIC: [O.GTE, O.LTE, O.GT, O.LT, O.EQUALS, O.DNEQUAL],
    Kinds.BOOLEAN: [O.IS, O.ISNOT],
    Kinds.DATE   : [O.IS, O.ISNOT, O.GT, O.LT],
    Kinds.STRING : [O.EQUALS, O.DNEQUAL, O.STRTWITH, O.ENDSWITH, O.MATCHES, O.CONTAINS]
}


class Condition(object):
    def __init__(self, kind, attribute_key, operator, value):
        self.kind = kind
        self.attribute_key = attribute_key
        self.operator = operator
        self.value = value


    @classmethod
    def from_encoding(cls, mc:typing.Tuple[str, str, str, str]):
        kind_rep, attr_key, operator_rep, value = mc
        
        if kind_rep == 'BOOLEAN':
            kind = Kinds.BOOLEAN
        elif kind_rep == 'DATE':
            kind = Kinds.DATE
        elif kind_rep == 'NUMERIC':
            kind = Kinds.NUMERIC
        else:
            kind = Kinds.STRING

        if operator_rep == 'GTE':
            operator = Operators.GTE
        elif operator_rep == 'LTE':
            operator = Operators.LTE
        elif operator_rep == 'GT':
            operator = Operators.GT
        elif operator_rep == 'LT':
            operator = Operators.LT
        elif operator_rep == 'IS':
            operator = Operators.IS
        elif operator_rep == 'ISNOT':
            operator = Operators.ISNOT
        elif operator_rep == 'EQUALS':
            operator = Operators.EQUALS
        elif operator_rep == 'DNEQUAL':
            operator = Operators.DNEQUAL
        elif operator_rep == 'STRTWITH':
            operator = Operators.STRTWITH
        elif operator_rep == 'ENDSWITH':
            operator = Operators.ENDSWITH
        elif operator_rep == 'MATCHES':
            operator = Operators.MATCHES

        if kind == Kinds.BOOLEAN:
            value = value in TRUISH
        elif kind == Kinds.NUMERIC:
            value == float(value)
            if abs(value) - math.floor(abs(value))  < FLOAT_TOLERANCE:
                value = int(value)
        elif kind == Kinds.DATE:
            pass # TODO figure out date serialization mechanics
        elif operator == Operators.MATCHES:
            value = re.compile(value)
        
        return cls(kind, attr_key, operator, value)