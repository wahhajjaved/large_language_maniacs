
# coding=utf-8

from game import *
from itertools import product, permutations


def number_alive(n):
    return n > 0 and n < 5


class Sticks(Game):

    def __init__(self,
        opt_pass=False,
        opt_wrap=False,
        opt_split_odd=False,
        opt_split_even=False):
        self.opt_pass = opt_pass
        self.opt_wrap = opt_wrap
        self.opt_split_odd = opt_split_odd
        self.opt_split_even = opt_split_even

    @staticmethod
    def primitive(state):
        if not number_alive(state[0][0]) and not number_alive(state[0][1]):
            return Game.LOSE
        if not number_alive(state[0][0]) and not number_alive(state[0][1]):
            return Game.WIN
        return Game.UNDETERMINED

    @staticmethod
    def initial_state():
        return ((1, 1), (1, 1))

    def transitions(self, state):
        ts = []
        if number_alive(state[0][0]):
            if number_alive(state[1][0]):
                ts.append('ll')
            if number_alive(state[1][1]):
                ts.append('lr')
        if number_alive(state[0][1]):
            if number_alive(state[1][0]):
                ts.append('rl')
            if number_alive(state[1][1]):
                ts.append('rr')
        if self.opt_pass:
            ts.append('pass')
        if number_alive(state[0][0]) and not number_alive(state[0][1]):
            # Split left
            if state[0][0] % 2: # Odd
                if self.opt_split_odd:
                    ts.append('split-l')
                    ts.append('split-l\'') # Complement
            elif self.opt_split_even:
                ts.append('split-l')
        if not number_alive(state[0][0]) and number_alive(state[0][1]):
            # Split right
            if state[0][0] % 2: # Odd
                if self.opt_split_odd:
                    ts.append('split-r')
                    ts.append('split-r\'') # Complement
            elif self.opt_split_even:
                ts.append('split-r')
        return ts

    def next(self, state, transition):
        if transition == 'll':
            if self.opt_wrap:
                return (((state[1][0] + state[0][0]) % 5, state[1][1]),
                        (state[0][0], state[0][1]))
            return ((state[1][0] + state[0][0], state[1][1]),
                    (state[0][0], state[0][1]))
        elif transition == 'lr':
            if self.opt_wrap:
                return ((state[1][0], (state[1][1] + state[0][0]) % 5),
                        (state[0][0], state[0][1]))
            return ((state[1][0], state[1][1] + state[0][0]),
                    (state[0][0], state[0][1]))
        elif transition == 'rl':
            if self.opt_wrap:
                return (((state[1][0] + state[0][1]) % 5, state[1][1]),
                        (state[0][0], state[0][1]))
            return ((state[1][0] + state[1][0], state[1][1]),
                    (state[0][0], state[0][1]))
        elif transition == 'rr':
            if self.opt_wrap:
                return ((state[1][0], (state[1][1] + state[0][1]) % 5),
                        (state[0][0], state[0][1]))
            return ((state[1][0], state[1][1] + state[1][0]),
                    (state[0][0], state[0][1]))
        elif transition == 'pass':
            return ((state[1][0], state[1][1]),
                    (state[0][1], state[0][0]))
        elif transition == 'split-l':
            return ((state[1][0], state[1][1]),
                    (state[0][0] / 2, state[0][0] - state[0][0] / 2))
        elif transition == 'split-l\'':
            return ((state[1][0], state[1][1]),
                    (state[0][0] - state[0][0] / 2, state[0][0] / 2))
        elif transition == 'split-r':
            return ((state[1][0], state[1][1]),
                    (state[0][1] / 2, state[0][1] - state[0][1] / 2))
        elif transition == 'split-r\'':
            return ((state[1][0], state[1][1]),
                    (state[0][1] - state[0][1] / 2, state[0][1] / 2))

    @staticmethod
    def describe(state):
        return u'[ ↑ %s %s ↑ | ↓ %s %s ↓ ]' % (
            state[0][0] if number_alive(state[0][0]) else 'x',
            state[0][1] if number_alive(state[0][1]) else 'x',
            state[1][0] if number_alive(state[1][0]) else 'x',
            state[1][1] if number_alive(state[1][1]) else 'x')
