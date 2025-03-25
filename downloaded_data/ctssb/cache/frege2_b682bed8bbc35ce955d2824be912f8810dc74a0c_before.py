# -*- coding: utf-8 -*-
"""
Code for handling classical propositional logic formulas.
"""

from string import ascii_lowercase
import re

# Connectives
NEG = '~'
CON = u'·'
DIS = u'∨'
IMP = u'⊃'
EQV = u'≡'
# Quantifiers
ALL = u'∀'
EXS = u'∃'
#CON = '&'
#DIS = '|'
#IMP = '>'
#EQV = '='

BINARY_CONNECTIVES = set([CON, DIS, IMP, EQV])
COMMUTATIVE = set([CON, DIS, EQV])
QUANTIFIERS = set([ALL, EXS])

class Option(object):

    def __init__(self, num, desc):
        self.num = num
        self.desc = desc

    @classmethod
    def for_formula(cls):
        return [cls.Tautology, cls.Contingency, cls.Contradiction]

    @classmethod
    def for_argument(cls):
        return [cls.Valid, cls.Invalid]

    @classmethod
    def for_set(cls):
        return [cls.Consistent, cls.Inconsistent]

    def __unicode__(self):
        return self.desc

    __repr__ = __unicode__
    __str__ = __unicode__

# options
Tautology = Option(1, 'טאוטולוגיה')
Contingency = Option(2, 'קונטינגנציה')
Contradiction = Option(3, 'סתירה')
Valid = Option(4, 'תקף')
Invalid = Option(5, 'בטל')
Consistent = Option(6, 'עקבית')
Inconsistent = Option(7, 'לא עקבית')

FORMULA_OPTIONS = [Tautology, Contingency, Contradiction]
SET_OPTIONS = [Consistent, Inconsistent]
ARGUMENT_OPTIONS = [Valid, Invalid]

class Formula(object):

    def __init__(self, string):
        string = string.strip()
        self._analyze(string)
        self._validate()

    def _analyze(self, string):
        if not string:
            raise ValueError('formula cannot be empty')

        self.con = None
        self.sf1 = None
        self.sf2 = None
        self.literal = self._strip(string.replace(' ',''))

        self._deep_analyze()

    def _deep_analyze(self):
        nesting = 0
        if (len(self.literal) == 1):
            # atomic formula
            return
        for i, c in enumerate(self.literal):
            if c == '(':
                nesting += 1
                # validate next char
                nxt = self.literal[i+1]
                if not self._is_valid_first_letter(nxt):
                    raise ValueError("illegal character %s after %s" % (nxt, c))
            elif c == ')':
                nesting -= 1
            elif nesting == 0:
                try:
                    # highest nesting level, check for main connective
                    if c in BINARY_CONNECTIVES:
                        # binary connective, create 2 sub formulas and return
                        self.con = c
                        literals = self.literal[:i], self.literal[i+1:]
                        self.sf1 = self.__class__(literals[0])
                        self.sf2 = self.__class__(literals[1])
                        # check that sub formulas are properly formed
                        for i, sf in enumerate([self.sf1, self.sf2]):
                            literal = literals[i]
                            if sf.is_binary and self._strip(literal) == literal:
                                raise ValueError('missing parentheses in sub formula %s' % literal) 
                        return
                    if c == NEG:
                        # unary connective, create 1 sub formula
                        if self.con:
                            # concatenated negations, sub formula was already created
                            assert self.sf1
                        else:
                            self.con = c
                            self.sf1 = self.__class__(self.literal[i+1:])
                            # do not return here since a binary connective might be found
                            # later and, if so, that would be the main connective
                except ValueError:
	            raise ValueError('invalid syntax %s' % self.literal)
            elif nesting < 0:
                raise ValueError('unbalanced parentheses %s' % self.literal)
        if self.con == NEG:
            # if this formula is a negation, make sure all literals were consumed
            if self.literal[0] != self.con or self.sf1.literal != self._strip(self.literal[1:]):
                raise ValueError('ill-formed negation formula %s' % self.literal)
        if nesting != 0:
            raise ValueError('unbalanced parentheses %s' % self.literal)

    def _strip(self, string):
        """ strip all outmost brackets of a string representation of a formula """
        if not string:
            return string
        if string[0] == '(' and string[-1] == ')':
            # brackets detected on both end side, but we must make sure they actually are the outer
            # most ones, and not a case like '(p&q)&(r&s)', which should not be stripped
            nesting = 0
            for i, c in enumerate(string):
                if c == ')':
                    nesting -= 1
                    if nesting == 0:
                        # closure found for the opening bracket, only strip if it's last
                        if i == (len(string) - 1):
                            # strip recursively
                            return self._strip(string[1:-1])
                        return string
                elif c == '(':
                    nesting += 1
        return string 

    def _validate(self):
        if self.is_atomic:
            assert not self.sf1 and not self.sf2
            if len(self.literal) == 0:
                raise ValueError('empty formula')
            if not self._is_valid_atomic():
                raise ValueError('%s is not a valid atomic formula' % self.literal)
        else:
            assert len(self.literal) > 1
            # validate of sub formulas is not called here since it is called while creating them above
            assert self.sf1
            if self.con in BINARY_CONNECTIVES:
                assert self.sf2

    def _is_valid_first_letter(self, letter):
        return letter.islower() or letter.isupper() or letter == NEG or letter == '('

    def _is_valid_atomic(self):
        return len(self.literal) == 1 and (self.literal.islower() or self.literal.isupper())

    @classmethod
    def from_set(cls, formula_set):
        f_str = ''
        for f in formula_set.formulas:
            if not f_str:
                f_str = f.literal
            else:
                f_str = '(%s)%s(%s)' % (f_str, CON, f.literal)
        return cls(f_str)

    @classmethod
    def from_argument(cls, argument):
        if argument.premises:
            return cls('(%s)%s(%s)' % (cls.from_set(argument.premises).literal, IMP, argument.conclusion.literal))
        return argument.conclusion

    @property
    def variables(self):
        """ return a list of variables, merged and sorted """
        if not hasattr(self, '_vars'):
            var_list = self._var_list()
            var_list = list(set(var_list))
            var_list.sort()
            self._vars = var_list
        return self._vars

    def _var_list(self):
        """ return a list of variables, not merged """
        if self.is_atomic:
            return [self.literal]
        if self.is_unary:
            return self.sf1._var_list()
        # binary
        return self.sf1._var_list() + self.sf2._var_list() 

    def assign(self, assignment):
        if len(self.variables) > len(assignment):
            raise ValueError('incorrect assignment size, should be %d' % len(self.variables))
        if any (v not in assignment for v in self.variables):
            raise ValueError('missing variables in assignment %s' % assignment)
        if self.is_atomic:
            return assignment[self.literal]
        if self.con == NEG: 
            return not self.sf1.assign(assignment)
        elif self.con == CON:
            return self.sf1.assign(assignment) and self.sf2.assign(assignment)
        elif self.con == DIS:
           return  self.sf1.assign(assignment) or self.sf2.assign(assignment)
        elif self.con == IMP:
           return  not self.sf1.assign(assignment) or self.sf2.assign(assignment)
        elif self.con == EQV:
           return  self.sf1.assign(assignment) == self.sf2.assign(assignment)

    def options(self):
        return FORMULA_OPTIONS

    @property
    def correct_option(self):
        tt = TruthTable(self)
        options = set([Tautology, Contradiction])
        for satisfied in tt.result:
            if not satisfied and Tautology in options:
                options.remove(Tautology)
            elif satisfied and Contradiction in options:
                options.remove(Contradiction)
            if not options:
                return Contingency
        assert len(options) == 1
        return options.pop()

    @property
    def is_tautology(self):
        return self.correct_option == Tautology

    @property
    def is_contradiction(self):
        return self.correct_option == Contradiction

    @property
    def is_atomic(self):
        return not self.con

    @property
    def is_unary(self):
        return self.con == NEG

    @property
    def is_binary(self):
        return self.con in BINARY_CONNECTIVES

    def __eq__(self, other):
        if not isinstance(other, Formula):
            return False
        if self.literal == other.literal:
            return True
        if not self.con:
            return False
        if self.con == other.con:
            if self.sf1 == other.sf1 and self.sf2 == other.sf2:
                return True
            if self.con in COMMUTATIVE and self.sf1 == other.sf2 and self.sf2 == other.sf1:
                return True
        return False

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash(self.literal)

    def __unicode__(self):
        return self.literal.encode('utf-8')

    def __str__(self):
        return self.literal.encode('utf-8')

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self)

    #__str__ = __unicode__

class PredicateFormula(Formula):

    def _deep_analyze(self):
        self.quantifier = None
        self.quantified = None
        if self.literal[0] in QUANTIFIERS and self._quantifier_range() == self.literal[2:]:
            if len(self.literal) < 4: # quantifier + var + atomic
                raise ValueError('formula too short: %s' % self.literal)
            self.quantifier = self.literal[0]
            self.quantified = self.literal[1]
            if not self.quantified.islower():
                raise ValueError('illegal quantified variable: %s' % self.quantified)
            self.sf1 = PredicateFormula(self.literal[2:])
        else:
            super(PredicateFormula, self)._deep_analyze()

    def _quantifier_range(self):
        return quantifier_range(self.literal)
                
    def _is_valid_first_letter(self, letter):
        return super(PredicateFormula, self)._is_valid_first_letter(letter) or letter in QUANTIFIERS

    def _is_valid_atomic(self):
        return is_valid_atomic(self.literal)

    @property
    def is_atomic(self):
        return not self.con and not self.quantifier

    @property
    def variables(self):
        raise NotImplementedError()

    @property
    def predicates(self):
        if self.is_atomic:
            return [self.literal[0]]
        if self.quantifier or self.con == NEG:
            return self.sf1.predicates
        return list(set(self.sf1.predicates + self.sf2.predicates))
 
    @property
    def constants(self):
        return self._constants()

    def _constants(self, other_than=[]):
        if self.is_atomic:
            return [c for c in self.literal[1:] if c not in other_than]
        if self.quantifier:
            return self.sf1._constants(other_than=other_than+[self.quantified])
        if self.con == NEG:
            return self.sf1._constants(other_than=other_than)
        return list(set(self.sf1._constants(other_than=other_than) + self.sf2._constants(other_than=other_than)))
 
    def _var_list(self):
        raise NotImplementedError()

    def assign(self, assignment):
        """ assignment should contain domain, every predicate and every constant in the formula """

        if self.is_atomic:
            predicate = self.literal[0]
            terms = self.literal[1:]
            term_values = tuple(assignment[t] for t in terms) if len(terms) > 1 else assignment[terms[0]]

            # check that the predicate assignment is legal
            if type(term_values) == tuple:
                assert all(type(v) == tuple and len(v) == len(term_values) for v in assignment[predicate]),\
                    'assignment does not match predicate %s' % predicate
            else: 
                assert all(type(v) in (str,int) for v in assignment[predicate]),\
                    'assignment does not match predicate %s' % predicate

            return term_values in assignment[predicate]

        if self.quantifier:
            for d in assignment['domain']:
                assignment[self.quantified] = d
                result = self.sf1.assign(assignment)
                if self.quantifier == ALL and not result:
                    # falsifies all
                    return False
                if self.quantifier == EXS and result:
                    # verifies exs
                    return True
            # no falsification of all or verification of exs was found
            return self.quantifier == ALL 

        if self.con == NEG: 
            return not self.sf1.assign(assignment)
        elif self.con == CON:
            return self.sf1.assign(assignment) and self.sf2.assign(assignment)
        elif self.con == DIS:
           return  self.sf1.assign(assignment) or self.sf2.assign(assignment)
        elif self.con == IMP:
           return  not self.sf1.assign(assignment) or self.sf2.assign(assignment)
        elif self.con == EQV:
           return  self.sf1.assign(assignment) == self.sf2.assign(assignment)
 
    def options(self):
        raise NotImplementedError()

    @property
    def correct_option(self):
        raise NotImplementedError()

    @property
    def is_tautology(self):
        raise NotImplementedError()

    @property
    def is_contradiction(self):
        raise NotImplementedError()

    def __eq__(self, other):
        if super(PredicateFormula, self).__eq__(other):
            return True
        if not isinstance(other, PredicateFormula):
            return False
        if self.literal == other.literal:
            return True
        if self.quantifier and self.quantifier == other.quantifier and len(self.literal) == len(other.literal):
            if self.quantified != other.quantified:
                new_var = get_new_var([self, other])
                other_inner_range = other._quantifier_range().replace(other.quantified, new_var)
                self_inner_range = self._quantifier_range().replace(self.quantified, new_var)
            else:
                other_inner_range = other._quantifier_range()
                self_inner_range = self._quantifier_range()
            other_inner = PredicateFormula(other_inner_range)
            self_inner = PredicateFormula(self_inner_range)
            return self_inner == other_inner
        return False

##########################################################################
# Predicate formula utils

def quantifier_range(string):
    if len(string) > 3 and string[0] in QUANTIFIERS:
        start = string[2]
        remaining = string[2:]
        # case 1: quantified expression is in brackets
        if start == '(':
            qrange = ''
            stack = []
            for s in remaining:
                qrange += s
                if s == '(':
                    stack.append(s)
                elif s == ')':
                    stack.pop()
            if len(stack) == 0:
                return qrange
        # case 2: quantified expression is a negation
        elif start == NEG:
            return start + quantifier_range(string.replace('~','',1))
        # case 3: quantified expression starts with a quantifier
        elif start in QUANTIFIERS:
            remaining_range = quantifier_range(remaining)
            if not remaining_range:
                raise ValueError('illegal quantified expression: %s' % string)
            return remaining[:2] + remaining_range
        # case 4: quantified expression is atomic - find its end
        else:
            i = 0
            qrange = ''
            while is_valid_atomic(remaining[:i+2]) and i < len(string) - 3:
                qrange = remaining[:i+2]
                i += 1
            return qrange
                
def is_valid_atomic(string):
    if len(string) > 1 and string[0].isupper():
        for c in string[1:]:
            if not c.islower():
                return False
        return True
    return False

def get_new_var(formulas):
    for c in ascii_lowercase:
        if all (c not in f.literal for f in formulas):
            return c

##########################################################################

class TruthTable(object):

    def __init__(self, formula):
        self.formula = formula
        self.variables = formula.variables
        self.values = self._values(self.variables)

    @property
    def size(self):
        return len(self.values)

    @property
    def result(self):
        return [
            self.formula.assign({
                var : value for var, value in zip(self.variables, var_values)
            })
            for var_values in self.values
        ]

    def _values(self, variables):
        values = []
        num_rows = 2**len(variables)
        num_cols = len(variables)
        for i in range(num_rows):
            row = []
            for j in range(num_cols):
                streak = 2**j
                relative = i % (streak * 2)
                row.insert(0, relative < streak)
            values.append(row)
        return values

class MultiTruthTable(TruthTable):

    def __init__(self, formulas):
        super(MultiTruthTable, self).__init__(formulas[0])
        self.formulas = formulas
        self.variables = list(set([v for var_list in [f.variables for f in formulas] for v in var_list]))
        self.variables.sort()
        self.values = self._values(self.variables)

    @property
    def result(self):
        result = []
        for f in self.formulas:
            self.formula = f
            result.append(super(MultiTruthTable, self).result)
        return result
            
class FormulaSet(object):

    SEP = ','

    def __init__(self, string = None, formulas = None, formula_cls = Formula):
        self.formula_cls = formula_cls
        if not string and not formulas:
            raise ValueError('formula set cannot be empty')
        if string:
            self.formulas = [self.formula_cls(p) for p in string.split(self.SEP)]
        else:
            self.formulas = formulas
        self.formulas = self._uniqify(self.formulas)
        self.literal = self.SEP.join(f.literal for f in self.formulas)

    def _uniqify(self, formulas):
        """ remove duplicates from a list while preserving order """
        seen = set()
        return [f for f in formulas if not (f in seen or seen.add(f))]

    @property
    def display(self):
        return '{%s}' % self.literal.replace(self.SEP,'%s ' % self.SEP)

    def options(self):
        return SET_OPTIONS

    @property
    def correct_option(self):
        if not self.formula_cls == Formula:
            raise NotImplementedError()
        if Formula.from_set(self).is_contradiction:
            return Inconsistent
        return Consistent

    @property
    def is_consistent(self):
        if not self.formula_cls == Formula:
            raise NotImplementedError()
        return self.correct_option == Consistent

    def __iter__(self):
        return iter(self.formulas)

    def __len__(self):
        return len(self.formulas)

    def __getitem__(self, key):
        return self.formulas[key]

    def __eq__(self, other):
        return self.formulas == other.formulas

    def __ne__(self, other):
        return not self == other

    def __unicode__(self):
        return self.literal.encode('utf-8')

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self)

    __str__ = __unicode__

class Argument(object):

    THEREFORE = u'∴'

    def __init__(self, string = None, conclusion = None, premises = None, formula_cls = Formula):
        self.formula_cls = formula_cls
        if string:
            self._analyze(string)
        else:
            self.conclusion = conclusion
            self.premises = FormulaSet(formulas=premises, formula_cls=self.formula_cls)

    def _analyze(self, string):
        try:
            premises, conclusion = string.split(self.THEREFORE)
            self.conclusion = self.formula_cls(conclusion)
            if premises:
                self.premises = FormulaSet(string=premises, formula_cls=self.formula_cls)
                premises_literal = self.premises.literal 
            else:
                self.premises = []
                premises_literal = ''
            self.literal = '%s%s%s' % (premises_literal, self.THEREFORE, self.conclusion.literal)
        except Exception, e:
            raise ValueError('illegal argument: %r' % string)

    @property
    def display(self):
        return self.literal.replace(FormulaSet.SEP,'%s ' % FormulaSet.SEP).replace(self.THEREFORE, ' %s ' % self.THEREFORE)

    @property
    def options(self):
        return ARGUMENT_OPTIONS

    @property
    def correct_option(self):
        if not self.formula_cls == Formula:
            raise NotImplementedError()
        if Formula.from_argument(self).is_tautology:
            return Valid
        return Invalid
        
    @property
    def is_valid(self):
        if not self.formula_cls == Formula:
            raise NotImplementedError()
        return self.correct_option == Valid

    def __iter__(self):
        return iter(list(self.premises) + [self.conclusion])

    def __getitem__(self, key):
        return self.conclusion

    def __eq__(self, other):
        return self.conclusion == other.conclusion and self.premises == other.premises

    def __ne__(self, other):
        return not self == other

    def __unicode__(self):
        return self.literal.encode('utf-8')

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self)

    __str__ = __unicode__

def formal_type(string):
    if Argument.THEREFORE in string:
        return Argument
    elif FormulaSet.SEP in string:
        return FormulaSet
    try:
        PredicateFormula(string)
        return PredicateFormula
    except:
        return Formula

def formalize(string):
    """
    takes a string representing a formula, a formula set, or an argument
    and returns the appropriate object
    """
    ftype = formal_type(string)
    if ftype in [Argument, FormulaSet]:
        try: 
            return ftype(string, formula_cls=PredicateFormula)
        except:
            pass
    return ftype(string)

def get_argument(string):
    a = formalize(string)
    assert type(a) == Argument
    return a

