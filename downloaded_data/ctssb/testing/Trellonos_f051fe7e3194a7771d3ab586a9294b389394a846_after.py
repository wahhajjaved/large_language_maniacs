import os
import json

from trello import TrelloApi
import requests

API_VERSION = '1'
BASE_URL = 'https://api.trello.com/' + API_VERSION + '/'

FILTER_OPEN = 'open'
FILTER_CLOSED = 'closed'
FILTER_ALL = 'all'

# CONVENIENCE CONVERSION FUNCTIONS


def boolean_to_string(boolean):
    if boolean:
        return "true"
    else:
        return "false"


class Trello(object):
    """ Wrapper of the Trello API """

    def __init__(self, api_key, token=None):
        # Store the API key and token for things the Python API can't do
        self.__api_key = api_key
        self.__token = token

        # Make a Trello Python API wrapper object for the things it CAN do
        self.__trello = TrelloApi(api_key, token)

        # Retrieve this Trello user
        self.__member = self.__trello.members.get('me')

    @classmethod
    def from_environment_vars(cls):
        # Construct a Trello wrapper using environment variable settings
        api_key = os.environ['TRELLONOS_API_KEY']
        token = os.environ['TRELLONOS_TOKEN']
        return cls(api_key, token)

    # PROPERTIES #
    @property
    def member(self):
        return self.__member

    # REQUESTS HELPERS #

    def request_params(self, extra_params={}):
        """ Generates the params dictionary for a trello HTTP request of the
        given parameters. """

        # Add the authentification params
        params = {
            'key': self.__api_key,
            'token': self.__token
        }

        # Add the given params
        for param in extra_params:
            params[param] = extra_params[param]

        return params

    # BOARDS #

    def get_boards(self, board_filter=FILTER_OPEN):
        """ Retrieves an optionally filtered list of Trello boards """

        boards = self.__trello.members.get_board(
            self.__member['id'], filter=board_filter)

        return boards

    # LISTS #

    def get_lists(self, board, list_filter=FILTER_OPEN):
        """ Retrieves an optionally filtered list of Trello lists """

        lists = self.__trello.boards.get_list(board['id'], filter=list_filter)

        return lists

    def update_list_name(self, list, name):
        """ Changes the name of a list """
        self.__trello.lists.update_name(list['id'], name)

    def update_list_closed(self, list, value):
        """ Opens or closes a list """
        self.__trello.lists.update_closed(list['id'],
                                          boolean_to_string(value))

    def create_list(self, board, list_name):
        """ Creates a new list in the given board """
        return self.__trello.boards.new_list(board['id'], list_name)

    def sort_list(self, list, position):
        """ Sorts the given list to the given position. Position can be
        'top' or 'bottom' or a positive number """

        url = BASE_URL + 'lists/' + list['id'] + '/pos'
        requests.put(url, params=self.request_params({'value': position}))

    def copy_list(self, list, board, override_params={}):
        """ Copies the given list into a new list in the given board """
        url = BASE_URL + 'lists/'

        params = {}

        params['name'] = list['name']
        params['idBoard'] = board['id']
        params['idListSource'] = list['id']

        for override_param in override_params:
            params[override_param] = override_params[override_param]

        request = requests.post(url, data=self.request_params(params))

        # Return the output
        return json.loads(request.text)

    # CARDS #

    def get_cards(self, list, card_filter=FILTER_ALL, fields=None):
        """ Retrieves cards from the given list """

        cards = self.__trello.lists.get_card(
            list['id'], filter=card_filter, fields=fields)

        return cards

    def create_card(self, list, card_name, description=''):
        """ Creates a new Trello card with a name and optional description """
        return self.__trello.cards.new(card_name, list['id'], description)

    def delete_card(self, card):
        """ Deletes a Trello card completely """
        self.__trello.cards.delete(card['id'])

    def update_card_name(self, card, name):
        """ Renames a Trello card """
        self.__trello.cards.update_name(card['id'], name)

    def update_card_description(self, card, description):
        """ Changes the description of a Trello card """
        self.__trello.cards.update_desc(card['id'], description)

    def update_card_closed(self, card, value):
        """ Changes the archival status of a card (open/closed) """
        self.__trello.cards.update_closed(card['id'],
                                          boolean_to_string(value))

    def add_card_member(self, card, member):
        """ Adds a member to a card, subscribing them to notifications
        from it """
        self.__trello.cards.new_member(card['id'], member['id'])

    def subscribe_card(self, card):
        """ Adds the member running Trellonos to a card """
        self.add_card_member(card, self.__member)

    def remove_card_member(self, card, member):
        """ Removes a member from a Trello card """
        self.__trello.cards.delete_member_idMember(member['id'], card['id'])

    def unsubscribe_card(self, card):
        """ Removes the member running Trellonos from a card """
        self.remove_card_member(card, self.__member)

    def move_card(self, card, list):
        """ Moves a card to a new list """
        # TODO this doesn't work
        url = BASE_URL + 'cards/' + card['id'] + '/idList'
        params = self.request_params({'value': list['id']})

        requests.put(url, params=params)

    def copy_card(self, card, list, override_params={}):
        """ Copies the given card into a new card in the given list """
        url = BASE_URL + 'cards/'

        params = {}

        params['due'] = card['due']
        params['idList'] = list['id']
        params['urlSource'] = 'null'
        params['idCardSource'] = card['id']

        for override_param in override_params:
            params[override_param] = override_params[override_param]

        request = requests.post(url, data=self.request_params(params))

        # Return the output
        return json.loads(request.text)
