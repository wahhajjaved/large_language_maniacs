# -*- coding: utf-8 -*-
# Copyright © 2013 Jens Schmer, Michael Engelhard

from NegamaxPlayer import NegamaxPlayer
from Board import Board
import cProfile as cp

def run():
    board = Board("""
                    1 W
                    kp...
                    .p...
                    .....
                    .....
                    .Q...
                    ...K.
                    """)
    player = NegamaxPlayer()
    best_move = player.negamax(board, 6, True)

    

if __name__ == '__main__':
    cp.run("run()", sort="time")