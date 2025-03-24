import sys
import os

# make sure wheelofjeopardy module is available on the load path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from wheelofjeopardy.events import Events
from wheelofjeopardy.player_state import PlayerState
from wheelofjeopardy.game_state import GameState
from wheelofjeopardy.text_helper import apostrophize, pluralize
from wheelofjeopardy.utils.read_configs import ReadCfgToOptions

class TextGUI(object):
    @classmethod
    def start(cls):
        print 'Welcome to Wheel of Jeopardy!'
        print "Let's get started!"
        global opts

        events = Events()
        opts = ReadCfgToOptions()
        TextGUI(cls._create_game_state(events), events)._start()

    # private static

    @classmethod
    def _create_game_state(cls, events):
        players = [PlayerState(opts.playerNames[n], events, opts.startScores[n])
                   for n in range(opts.nPlayers)]
        return GameState(players, events, opts)

    @staticmethod
    def _clear_terminal():
        raw_input("Press Enter to continue...")
        os.system('cls' if os.name=='nt' else 'clear')

    # public instance

    def __init__(self, game_state, events):
        self.game_state = game_state
        self.events = events

    # private instance

    def _start(self):
        self.events.subscribe('game_state.current_player_did_change', self._on_current_player_did_change)
        self.events.subscribe('game_state.spins_did_update', self._on_spins_did_update)
        self.events.subscribe('game_state.turn_will_end', self._on_turn_will_end)
        self.events.subscribe('game_state.sector_was_chosen', self._on_sector_was_chosen)

        self.events.subscribe('board_sector.question_will_be_asked', self._on_question_will_be_asked)
        self.events.subscribe('board_sector.check_answer', self._on_check_answer)

        TextGUI._clear_terminal()
        while self.game_state.any_spins_remaining():
            print(self.game_state.board)
            print 'What would you like to do, %s?' % self.game_state.get_current_player().name
            sys.stdout.write("(S)pin, (Q)uit, (P)rint scores: ")
            answer = raw_input().lower()

            if answer == 's':
                self.game_state.spin()
            elif answer == 'p':
                self._print_scores()
            elif answer == 'q':
                break

        print 'Good game!'

    def _on_current_player_did_change(self, game_state):
        print self._get_whose_turn_message()

    def _on_spins_did_update(self, game_state):
        print self._get_spins_remaining_message()

    def _on_sector_was_chosen(self, sector):
        print('You spinned %s.' % str(sector))
        TextGUI._clear_terminal()

    def _on_turn_will_end(self, game_state):
        print 'That concludes %s turn.' % apostrophize(game_state.get_current_player().name)

    def _on_question_will_be_asked(self, question):
        sys.stdout.write('%s: ' % (question[2].text))
        answer = raw_input()
        self.events.broadcast('gui.answer_received', answer)

    def _on_check_answer(self, question, answer):
        mod_response = ''

        while mod_response != 'y' and mod_response != 'n':
            player_name = self.game_state.get_current_player().name
            print 'Correct answer is: %s' % (question[2].answer)
            sys.stdout.write('Hey moderator, is %s answer correct (y/n)? ' % (apostrophize(player_name)))
            mod_response = raw_input()

        if mod_response == 'y':
            self.events.broadcast('gui.correct_answer_received', question)
        else:
            self.events.broadcast('gui.incorrect_answer_received', question)

    def _print_scores(self):
        score_strings = []

        for pl in self.game_state.player_states:
            score_strings.append("\t%s has %u points, %u tokens." % \
                                 (pl.name, pl.score, pl.free_spin_tokens) )

        print 'Here are the scores:'
        print '\n'.join(score_strings)
        TextGUI._clear_terminal()

    def _get_spins_remaining_message(self):
        spins = self.game_state.spins_remaining

        return "There %s remaining." % (
            pluralize(spins, 'is 1 spin', 'are %d spins' % spins)
        )

    def _get_whose_turn_message(self):
        return "It's %s turn." % apostrophize(self.game_state.get_current_player().name)

if __name__ == '__main__':
    TextGUI.start()
