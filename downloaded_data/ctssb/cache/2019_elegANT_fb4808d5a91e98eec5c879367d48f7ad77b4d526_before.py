import time
import sys

from src.controller.utils import create_thread

from src.model.player import Player
from src.model.game_state import GameState

from src.view.view import View

from src.settings import all_params


class Controller:
    def __init__(self):

        # self.player = Player()
        self.view = View(1300, 800)
        self.view.change_view_state(View.STARTVIEW)
        self.game_state = None

        self.event_list_start_view = {
            'start_button': self.start_button_pressed,
            'quit_game': self.exit_game
        }

        self.event_list_game_view = {
            'build_scout': self.create_ant,
            'quit_game': self.exit_game
        }

        self.event_list = {
            'start_view': self.event_list_start_view,
            'game_view': self.event_list_game_view
        }

    def start_button_pressed(self, color, player_name):
        """
        Event-handler for the start button to change Viewstate from Startview to Gameview
        :param color: Color chosen by player
        :param player_name: Name chosen by player
        :return: returns a game_state object for initialization of the game
        """
        if player_name:
            self.view.change_view_state(View.GAMEVIEW)
            player = Player(color, player_name)
            player_list = [player]
            game_state = GameState(player_list)
            return game_state
        else:
            # TODO Get view to show pop up with message
            print('Player name not entered')

    @staticmethod
    def exit_game():

        """
        Quit game method
        :return: nothing
        """
        sys.exit()

    def create_ant(self, button):
        """
        Event-handler for creating ants using the create ants button
        :param button: Create Ants button
        :return: nothing
        """
        if button.state != 'loading':
            button.state = 'loading'

            def _create_ant():
                time.sleep(all_params.controller_params.create_ant_time)
                nest = self.game_state.get_nests()[0]
                self.game_state.create_ants(nest, amount=1)
                self.view.increment_ant_count()

            create_thread(func=_create_ant)

    def get_events(self, view_state):

        """
        Function to get events from view and call the corresponding functions
        according to view_state

        :param view_state: String specifying state of view
        :return: nothing
        """

        # Get the list of events from view
        event_argument_list = self.view.events()

        # Getting events and arguments as two lists
        event = list(event_argument_list.keys())
        args = list(event_argument_list.values())
        for i in range(len(event)):
            if event[i] in self.event_list[view_state].keys():
                if args[i] is not None:
                    if view_state == 'start_view':
                        self.game_state = self.event_list[view_state][event[i]](*args[i])
                    else:
                        self.event_list[view_state][event[i]](*args[i])

    def game_state_init(self):
        """
        Function to initialize game state
        when game state is none
        :return: nothing
        """

        self.get_events('start_view')

    def game_state_update(self):
        """
        Function to update game state
        when game state is not none
        :return: nothing
        """

        self.view.update(self.game_state.get_objects_in_region(self.view.pos[0], self.view.pos[1]))
        self.get_events('game_view')
        self.game_state.update()

    def game_loop(self):
        """
        Main game loop
        :return: nothing
        """

        frame_rate = all_params.controller_params.framerate
        while True:

            current_time = time.time()

            if self.game_state is None:
                self.view.draw()
                self.game_state_init()

            else:
                self.view.draw()
                self.game_state_update()

            # For frame rate adjustment
            exit_time = time.time()
            time_elapsed = exit_time - current_time
            frames_per_sec = 1. / frame_rate
            time.sleep(max(frames_per_sec - time_elapsed, 0))

