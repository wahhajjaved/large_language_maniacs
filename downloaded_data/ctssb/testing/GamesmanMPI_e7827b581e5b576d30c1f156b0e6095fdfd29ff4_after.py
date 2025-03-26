from bitarray import bitarray
from functools import wraps
import src.utils

length, height = 8, 8
area = length * height
BLANK, WHITE, BLACK = 0, 2, 1
opponent = {BLACK:WHITE, WHITE:BLACK, BLANK:BLANK}
char_rep = {BLACK:"O", WHITE:"X", BLANK:"-"}

"""
WRAPPERS FOR DUMB HASHING PROBLEMS
"""
def unpackinput(func):
    # Unpacks bytes into bitarrays
    @wraps(func)
    def wrapper(by, *args):
        return func(bytes_to_board(by), *args)
    return wrapper

def packoutput(func):
    # Packs bitarrays into bytes
    @wraps(func)
    def wrapper(*args, **kwargs):
        return board_to_bytes(func(*args, **kwargs))
    return wrapper

"""
MAIN GAME LOGIC
"""
@packoutput
def initial_position():
    # The first length*height bits represent the white player's pieces
    # The second length*height bits represent the black player's pieces
    # The last two  groups of 8 bits represent the turn bit and the number of passes in a row
    initial_pos = bitarray(2 * area + 16)
    initial_pos[0:len(initial_pos)] = False
    board_set(initial_pos, length / 2 - 1, height / 2 - 1, WHITE)
    board_set(initial_pos, length / 2 - 1, height / 2, BLACK)
    board_set(initial_pos, length / 2, height / 2 - 1, BLACK)
    board_set(initial_pos, length / 2, height / 2, WHITE)

    # We need our board have have a length that's a multiple of eight, since we
    # convert it to a tuple of bytes
    padding = bitarray(len(initial_pos) % 8)
    padding.setall(False)

    return initial_pos + padding

@unpackinput
def primitive(board):
    def determine_winner():
        black_count = 0
        white_count = 0
        counts = [0, 0]
        for x in range(length):
            for y in range(height):
                if board_get(board, x, y) == BLACK:
                    black_count += 1
                elif board_get(board, x, y) == WHITE:
                    white_count += 1
        if black_count == white_count:
            return src.utils.TIE
        if (black_count > white_count) ^ (turn_count(board) == 1):
            return src.utils.LOSS
        return src.utils.WIN

    non_zero_count = 0

    for x in range(length):
        for y in range(height):
            if board_get(board, x, y) != BLANK:
                non_zero_count += 1

    if non_zero_count == area or pass_count(board) >= 2:
        return determine_winner()
    return src.utils.UNDECIDED

@unpackinput
@packoutput
def do_move(board, move):
    def flip_pieces(state,x,y):
        board_set(state, x, y, current_turn(board))
        dx = -1
        while dx <= 1:
            dy = -1
            while dy <= 1:
                if not (dx == 0 and dy == 0):
                    flip_helper(state, x+dx, y+dy, dx, dy)
                dy += 1
            dx += 1

    def flip_helper(state, x, y, dx, dy):
        if x >= height or y >= length or x < 0 or y < 0:
            return
        opponent_color = opponent[current_turn(state)]
        if board_get(state, x, y) != opponent_color:
            return
        to_flip = [(x, y)]
        flip_helper2(state,x+dx,y+dy,dx,dy,to_flip)

    def flip_helper2(state,x,y,dx,dy,to_flip):
        if x >= height or y >= length or x < 0 or y < 0:
            return
        if board_get(state, x, y) == current_turn(state):
            for i, j in to_flip:
                flip(state, i, j)
            return
        if board_get(state, x, y) == opponent[current_turn(state)]:
            to_flip.append((x,y))
            flip_helper2(state, x+dx, y+dy, dx, dy, to_flip)

    successor = board[:]
    #account for pass case
    if move == None:
        incr_pass(successor)
        return successor
    reset_pass(successor) # Since we didn't pass, reset the pass count

    x, y = move
    flip_pieces(successor, x, y)
    incr_turn(successor)
    return successor

@unpackinput
def gen_moves(board):
    def legit_move(x, y):
        if board_get(board, x, y) != BLANK:
            return False
        dx = -1
        while dx <= 1:
            dy = -1
            while dy <= 1:
                if not (dx == 0 and dy == 0):
                    if legit_helper(x+dx, y+dy, dx ,dy, True):
                        return True
                dy += 1
            dx += 1
        return False

    def legit_helper(x, y, dx, dy, first):
        if x >= length or y >= height or x < 0 or y < 0:
            return False
        opponent_color = opponent[current_turn(board)]
        if first:
            if board_get(board, x, y) != opponent_color:
                return False
            return legit_helper(x+dx,y+dy,dx,dy,False)
        if board_get(board, x, y) == current_turn(board):
            return True
        if board_get(board, x, y) == opponent_color:
            return legit_helper(x+dx,y+dy,dx,dy,False)
        return False

    possible_moves = []
    for x in range(length):
        for y in range(height):
            if legit_move(x, y):
                possible_moves.append((x, y))

    if len(possible_moves) == 0:
        possible_moves.append(None)
    return possible_moves

@unpackinput
def print_board(board):
    #prints the current board and players turn
    for x in range(length):
        row = ""
        for y in range(height):
            row = row + char_rep[board_get(board, x, y)]
        print(row)
    print("Player's turn: ", current_turn(board))

def example(num_times):
    import random

    print('the initial position is the following:')
    print_board(initial_position())
    possible_actions = gen_moves(initial_position())
    print('these are the possible actions:')
    print(possible_actions)
    print('primitive value:')
    print(primitive(initial_position()))

    for i in range(num_times):
        print("Starting game " + str(i))
        possible_actions = gen_moves(initial_position())
        board = initial_position()

        while primitive(board) == src.utils.UNDECIDED:
            action = random.randint(0,len(possible_actions) - 1)
            board = do_move(board, possible_actions[0])
            print_board(board)
            possible_actions = gen_moves(board)
            print('New possible actions:')
            print(possible_actions)
            print('primitive value:')
            print(primitive(board))


def primitive_example():
    import random
    board = initial_position()
    for x in range(length):
        for y in range(height):
            if random.randint(0,1) == 0:
                board_set(board, x, y, WHITE)
            else:
                board_set(board, x, y, BLACK)
    print_board(board)
    print("Primitive Value: " + src.utils.STATE_MAP[primitive(board)])

"""
HELPER FUNCTIONS FOR BIT MANIPULATION
STOP SCROLLING IF YOU CARE ABOUT READABILITY
"""
def board_to_bytes(board):
    return board.tobytes()

def bytes_to_board(data):
    a = bitarray(endian='big')
    a.frombytes(data)
    return a

def board_get(board, x, y):
    if board[int(length  * y + x)]:
        return WHITE
    elif board[int(area + length * y + x)]:
        return BLACK
    else:
        return BLANK

def board_set(board, x, y, color):
    w_index = int(length * y + x)
    b_index = int(area + length * y + x)
    if color == WHITE:
        board[w_index] = True
        board[b_index] = False
    elif color == BLACK:
        board[b_index] = True
        board[w_index] = False
    else:
        board[w_index] = False
        board[b_index] = False

def flip(board, x, y):
    board_set(board, x, y, opponent[board_get(board, x, y)])

def turn_count(board):
    start = 2 * area
    return int.from_bytes(board[start:start + 8].tobytes(), byteorder="big", signed=False)

def incr_turn(board):
    new_turn = (turn_count(board)) % 2 + 1
    start = 2 * area
    a = bitarray(endian='big')
    a.frombytes(new_turn.to_bytes(1, byteorder='big', signed=False))
    board[start:start + 8] = a

def reset_turn(board):
    start = 2 * area
    board[start:start + 8] = bitarray('00000000')

def pass_count(board):
    start = 2 * area + 8
    return int.from_bytes(board[start:start + 8].tobytes(), byteorder="big", signed=False)

def incr_pass(board):
    new_pass = pass_count(board) + 1
    start = 2 * area + 8
    a = bitarray(endian='big')
    a.frombytes(new_pass.tobytes(1, byteorder='big', signed=False))
    board[start:start + 8] = a

def reset_pass(board):
    start = 2 * area + 8
    board[start:start + 8] = bitarray('00000000')

def full(board):
    full_board = bitarray(area).setall(True)
    return board[0:area] | board[area: 2 * area] == full_board

def current_turn(board):
    return WHITE if turn_count(board) % 2  == 0 else BLACK
