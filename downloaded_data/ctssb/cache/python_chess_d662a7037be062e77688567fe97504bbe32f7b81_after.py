"""
Tests for the Knight class to ensure correct
placement, movement, capturing, and promotion
behavior, as well as correct attributes upon creation.

Last modified: 4/2/2018
Author: Daniel Edades
"""

import sys
import pytest
import random
sys.path.append("..")
from board import Board
from knight import Knight
from piece import PieceColor
from piece import IllegalPlacementException
from piece import IllegalMoveException


@pytest.fixture
def test_board():
    test_board = Board()
    return test_board


@pytest.fixture
def test_white_knight(test_board):
    starting_file = "b"
    starting_rank = 1
    starting_space = test_board.get_space(starting_file, starting_rank)
    test_knight = Knight(PieceColor.WHITE)
    test_knight.place(starting_space)
    return test_knight


@pytest.fixture
def test_black_knight(test_board):
    starting_file = "b"
    starting_rank = 8
    starting_space = test_board.get_space(starting_file, starting_rank)
    test_knight = Knight(PieceColor.BLACK)
    test_knight.place(starting_space)
    return test_knight


class TestCreateKnight:

    def test_create_white_knight(self, test_board, test_white_knight):
        assert test_white_knight
        assert test_white_knight.color is PieceColor.WHITE
        starting_file = "g"
        starting_rank = 1
        starting_space = test_board.get_space(starting_file, starting_rank)
        test_white_knight.place(starting_space)
        assert test_white_knight.current_space is starting_space

    def test_create_black_knight(self, test_board, test_black_knight):
        assert test_black_knight
        assert test_black_knight.color is PieceColor.BLACK
        starting_file = "g"
        starting_rank = 8
        starting_space = test_board.get_space(starting_file, starting_rank)
        test_black_knight.place(starting_space)
        assert test_black_knight.current_space is starting_space