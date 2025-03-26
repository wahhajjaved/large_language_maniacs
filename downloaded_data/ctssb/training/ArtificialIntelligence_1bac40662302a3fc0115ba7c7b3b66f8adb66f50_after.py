"""
PetDetectiveProblem.py
Represents the PetDetective problem, subclasses aima's Problem class.
"""

from copy import deepcopy
from prog2.aima.search import Problem

__author__ = "Chris Campell"
__version__ = "9/19/2017"


class PetDetectiveProblem(Problem):
    initial_state = None
    goal_state = None
    game_board = None
    pet_house_locations = None

    def __init__(self, initial_state, goal_state, game_board):
        super().__init__(initial=initial_state, goal=goal_state)
        self.game_board = game_board
        self.pet_house_locations = self.extract_pet_house_locations()
        # TODO: perform additional self.init as required.

    def extract_pet_house_locations(self):
        pet_house_locations = {}
        for i, row in enumerate(self.game_board):
            for j, ele in enumerate(row):
                if ele.isalpha():
                    if not ele.islower():
                        pet_house_locations[ele] = (i, j)
        return pet_house_locations

    def is_road(self, desired_location):
        """
        is_road: Returns if the desired location is a road ('-', '+', '|', {a-z,A-Z}).
        :param desired_location: The location to check for existence of a road in the form (x,y).
        :return boolean: True if the provided location is a road (may contain pet), false otherwise.
        """
        if self.game_board[desired_location[0]][desired_location[1]] != '.':
            return True
        else:
            return False

    def is_valid_action(self, agent_location, action):
        """
        is_valid_action: Determines if the specified action is executable based on the presence of the roadways and the
            map edge.
        :param action: The action that the agent wishes to perform in the context of the environment.
        :return boolean: True if the action is executable according to game rules, false otherwise.
        """
        if action == 'u':
            return self.is_road(desired_location=(agent_location[0] - 1, agent_location[1]))
        elif action == 'r':
            return self.is_road(desired_location=(agent_location[0], agent_location[1] + 1))
        elif action == 'd':
            return self.is_road(desired_location=(agent_location[0] + 1, agent_location[1]))
        elif action == 'l':
            return self.is_road(desired_location=(agent_location[0], agent_location[1] - 1))
        else:
            print("is_valid_action: Error, unknown agent action.")

    def actions(self, state):
        """
        actions: Returns the actions that can be executed in the given state.
        :param state: The state from which possible actions are to be determined.
        :return actions: A list of possible actions to be executed.
        """
        actions = []
        agent_loc = state['agent_loc']
        if self.is_valid_action(agent_location=agent_loc, action='u'):
            actions.append('u')
        if self.is_valid_action(agent_location=agent_loc, action='r'):
            actions.append('r')
        if self.is_valid_action(agent_location=agent_loc, action='l'):
            actions.append('l')
        if self.is_valid_action(agent_location=agent_loc, action='d'):
            actions.append('d')
        return actions

    def result(self, state, action):
        """
        result: Returns the state that results from executing the given action in the given state. The action
            must be one of self.actions(state).
        :param state: The initial state.
        :param action: The action to apply to the initial state.
        :return resultant_state: The state that results from executing the given action in the provided state.
        """
        resultant_state = deepcopy(state)
        if action in self.actions(state=state):
            # The action is valid and recognized.
            if action == 'u':
                updated_location = (state['agent_loc'][0] - 1, state['agent_loc'][1])
            elif action == 'r':
                updated_location = (state['agent_loc'][0], state['agent_loc'][1] + 1)
            elif action == 'l':
                updated_location = (state['agent_loc'][0], state['agent_loc'][1] - 1)
            elif action == 'd':
                updated_location = (state['agent_loc'][0] + 1, state['agent_loc'][1])
            else:
                print("This shouldn't happen.")
            for pet, pet_location in state['pets_in_street'].items():
                if updated_location == pet_location:
                    # Append the pet to the car:
                    resultant_state['pets_in_car'].append(pet)
                    # Remove the pet from the street:
                    resultant_state['pets_in_street'].pop(pet)
            # TODO: Double check implementation of pet dropoff.
            # Check to see if pet dropoff is necessary:
            if state['pets_in_car']:
                for pet_house, house_location in self.pet_house_locations.items():
                    if updated_location == house_location:
                        # The agent is at a pet's house:
                        if pet_house.lower() in state['pets_in_car']:
                            # The pet is in the car:
                            # Remove the pet from the car:
                            resultant_state['pets_in_car'].remove(pet_house.lower())
            resultant_state['agent_loc'] = updated_location
            return resultant_state

    def goal_test(self, state):
        """
        goal_test: Returns true if the state is a goal.
        :param state: The current state of the program represented by {'agent_loc': (x, y),
            'pets_in_car': [], 'pets_in_street': {'pet': (x, y), ...}}
        :return is_goal: True if the provided state is a goal state, false otherwise.
        """
        if len(state['pets_in_car']) == 0:
            if not state['pets_in_street']:
                return True
        return False

    def path_cost(self, c, state1, action, state2):
        """
        path_cost: Returns the cost of a solution path that arrives at state2 from state1 via action, assuming cost 'c'
            to arrive at state1.
        :param c: The cost of executing the given action (always 1 for pet detective).
        :param state1: The initial state.
        :param action: The action applied to the initial state which resulted in state2.
        :param state2: The state reached as a result of applying the given action to state1.
        :return path_cost: The cost of a solution path that arrives at state2 from state1 assuming cost 'c'.
        """
        return c

    def print_world(self, game_state):
        """
        print_world: Prints a human-readable version of the game board to the console.
        :return None: Upon completion; a human-readable string representation of the game state is printed to stdout.
        """
        # TODO: Finish this method by updating the pet locations and agent locations based on the current state.
        if game_state['pets_in_car']:
            # Remove pet from gameboard.
            for pet, loc in game_state['pets_in_car'].items():
                # Iterate through gamestate and find pet
                self.game_board[loc[0]][loc[1]] = '*'
                '''
                for i, row in enumerate(self.game_board):
                    for j, ele in enumerate(row):
                        if self.game_board[i][j] == pet:
                            # TODO: Observe the adjacent squares to determine if + or - or |
                            # For now just replace with *. 
                            self.game_board[i][j] = '*'
                '''
        # update agent location:
        '''
        for i, row in enumerate(self.game_board):
            for j, col in enumerate(row):
                if self.game_board[i][j] == '^':
                    if (i, j) == game_state['agent_loc']:
                        # The carrot is the current agent location, no update
                        pass
                    else:
                        row_copy_prepend = self.game_board[i][0:j]
                        row_copy_postpend = self.game_board[i][j+1:-1]
                        new_row = row_copy_prepend + '$' + row_copy_postpend
                        new_row[j] = '^'
                        self.game_board[i] = new_row

                        # self.game_board[i][j] = '$'
                        self.game_board[game_state['agent_loc'][0]][game_state['agent_loc'][1]] = '^'
        '''
        world_string = ''
        for i, row in enumerate(self.game_board):
            world_string = world_string + row + "\n"
        print(world_string)

