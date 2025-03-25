import requests

from . import constants, exceptions


class YGOProDeck:
    url_cardinfo = 'https://db.ygoprodeck.com/api/v2/cardinfo.php'
    url_pics = 'https://ygoprodeck.com/pics/'

    session = requests.Session()

    def make_request(self, url, **kwargs):
        response = self.session.get(url, **kwargs)

        response.raise_for_status()

        return response.json()

    def get_all_cards(self):
        return self.make_request(self.url_cardinfo)

    def get_cards(self, **params):
        """Get a list of cards.

        Args:
            name (str): The exact name of the card. You can also pass a card
                ID to this.
            fname (str): A fuzzy search using a string. For example &
                fname=Magician to search by all cards with "Magician" in the
                name.
            type_ (str): The type of card you want to filter by, type is a reserved word in python so use type_.
            atk (int): Filter by atk value.
            def_ (int): Filter by def value, def is a reserved word in python
                so use def_ to represente defense.
            level (int): Filter by card level/RANK.
            race (str): Filter by the card race which is officially called
                type (Spellcaster, Warrior, Insect, etc). This is also used
                for Spell/Trap cards.
            attribute (int): Filter by the card attribute.
            link (int): Filter the cards by Link value.
            linkmarker (str): Filter the cards by Link Marker value (Top,
                Bottom, Left, Right, Bottom-Left, Bottom-Right, Top-Left,
                Top-Right).
            scale (int): Filter the cards by Pendulum Scale value.
            set (str): Filter the cards by card set (Metal Raiders, Soul
                Fusion, etc).
            archetype (str): Filter the cards by archetype (Dark Magician,
                Prank-Kids, Blue-Eyes, etc).
            banlist (str): Filter the cards by banlist (TCG, OCG, Goat).
            sort (str): Sort the order of the cards (atk, def, name, type,
                level, id).
            la (str): Filter the cards by Language.

        Returns:
            (list[dict]): List of cards
        """
        params = self.validate_params(params)
        return self.make_request(self.url_cardinfo, params=params)

    def validate_params(self, params):
        if 'def_' in params.keys():
            params = self.change_defense_param_key(params)

        if 'type_' in params.keys():
            params = self.change_type_param_key(params)

        self.validate_type(params)
        self.validate_level_rank(params)

    @staticmethod
    def change_defense_param_key(params):
        try:
            params['def'] = params.pop('def_')
        except KeyError:
            pass

        return params

    @staticmethod
    def change_type_param_key(params):
        try:
            params['type'] = params.pop('type_')
        except KeyError:
            pass

        return params

    @staticmethod
    def validate_type(params):
        card_type = params.get('type')

        if card_type is not None:
            if card_type not in constants.TYPES:
                raise exceptions.TypeInvalid()

    @staticmethod
    def validate_level_rank(params):
        level = params.get('type')

        if level is not None:
            try:
                level = int(level)
            except ValueError:
                raise exceptions.LevelOrRankInvalid()

            if level not in range(0, 13):
                raise exceptions.LevelOrRankInvalid()

    @staticmethod
    def validate_race(params):
        race = params.get('race')

        if race is not None:
            if race not in constants.RACE:
                raise exceptions.RaceInvalid()
