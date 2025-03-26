from ..game import Game, InvalidMove, coord_in_mini_board

COLORS = {
        'default'    :    '\033[0m',

        'bold'       :    '\033[1m',
        'underline'  :    '\033[4m',
        'blink'      :    '\033[5m',
        'reverse'    :    '\033[7m',
        'concealed'  :    '\033[8m',

        'black'      :    '\033[30m',
        'red'        :    '\033[31m',
        'green'      :    '\033[32m',
        'yellow'     :    '\033[33m',
        'blue'       :    '\033[34m',
        'magenta'    :    '\033[35m',
        'cyan'       :    '\033[36m',
        'white'      :    '\033[37m',

        'on_black'   :    '\033[40m',
        'on_red'     :    '\033[41m',
        'on_green'   :    '\033[42m',
        'on_yellow'  :    '\033[43m',
        'on_blue'    :    '\033[44m',
        'on_magenta' :    '\033[45m',
        'on_cyan'    :    '\033[46m',
        'on_white'   :    '\033[47m' }

class ConsoleUi:
    def set_handler(self, handler):
        self._handler = handler

    def on_join_match_reply(self, reply, match):
        print('Joined match %s. Users: %s' % (match.match_id, match.users))

    def on_new_game(self, obj, game):
        self._char = obj['your_char']
        self.on_make_move(obj, game)

    def on_make_move(self, obj, game):
        self.print_game(game)
        if game.current_player == self._char:
            while not self.play(game):
                pass
        else:
            print('%s\'s turn.' % game.current_player)

    def print_game(self, game):
        if game.last_move is not None:
            (last_char, last_line, last_column) = game.last_move
            expected_mini_board = coord_in_mini_board(last_line, last_column)
            if game.mini_board_winner(*expected_mini_board) is not None:
                expected_mini_board = (-1, -1)
        else:
            expected_mini_board = (-1, -1)
        print('      1 2 3       4 5 6       7 8 9')
        print('  ' + ('+-----------'*3) + '+')
        letter = ord('A')
        for l1 in range(0, 3):
            mini_boards = []
            for c1 in range(0, 3):
                s = []
                color = ''
                winner = game.mini_board_winner(c1, l1)
                if (l1, c1) == expected_mini_board:
                    color = COLORS['on_blue']
                elif winner == 'X':
                    color = COLORS['on_red']
                elif winner == 'O':
                    color = COLORS['on_green']
                border = color + '  ' + COLORS['default']
                s.append(color + (' '*11) + COLORS['default'])
                s.append(border + '+-+-+-+' + border)
                for l2 in range(l1*3, l1*3+3):
                    s2 = border + '|'
                    for c2 in range(c1*3, c1*3+3):
                        if game.grid[l2][c2] == 'O':
                            s2 += COLORS['on_green']
                        elif game.grid[l2][c2] == 'X':
                            s2 += COLORS['on_red']
                        s2 += game.grid[l2][c2]
                        s2 += COLORS['default']
                        s2 += '|'
                    s2 += border
                    s.append(s2)
                    s.append(border + '+-+-+-+' + border)
                s.append(s[0])
                mini_boards.append(s)
            for (i, line) in zip([0, 0, 1, 0, 1, 0, 1, 0, 0], zip(*mini_boards)):
                if i:
                    prefix = chr(letter)
                    letter += 1
                else:
                    prefix = ' '
                print(prefix + ' |' + ('|'.join(line)) + '|')
            print('  ' + ('+-----------'*3) + '+')


    def play(self, game):
        move = input('Move? ')
        if len(move) != 2:
            print('Bad input. Should be a letter (line) and a digit(column)')
            return False
        (line, column) = move
        line = ord(line.lower()) - ord('a')
        if not (0 <= line <= 8):
            print('Invalid line.')
            return False
        if not column.isdigit() or not (1 <= int(column) <= 9):
            print('Invalid column.')
            return False
        column = int(column)-1


        try:
            game.make_move(line, column, apply_=False)
        except InvalidMove as e:
            print('Invalid move: %s' % e.args[0])
            return False
        else:
            self._handler.make_move(line, column)
            return True
