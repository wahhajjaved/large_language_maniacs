import datetime
import requests
import os
from model import MatchResult
from garprLogging.log import Log

### SMASHGG URLS: https://smash.gg/tournament/<tournament-name>/brackets/<event-id>/<group-id>/<phase-group-id>
BASE_SMASHGG_EVENT_API_URL = "https://api.smash.gg/event/"
BASE_SMASHGG_PHASE_API_URL = "https://api.smash.gg/phase_group/"
EVENT_URL = os.path.join(BASE_SMASHGG_EVENT_API_URL, '%s')
TOURNAMENT_URL = os.path.join(BASE_SMASHGG_PHASE_API_URL, '%s')
DUMP_SETTINGS_GROUPS = "?expand[0]=groups"
DUMP_SETTINGS_ALL = "?expand[0]=sets&expand[1]=entrants&expand[2]=matches&expand[3]=seeds"

class SmashGGScraper(object):
    def __init__(self, path):
        """
        :param path: url to go to the bracket
        """
        self.path = path

        #DETERMINES IF A SCRAPER IS FOR A POOL
        #PREVENTS INFINITE RECURSION
        self.is_pool = False

        #GET IMPORTANT DATA FROM THE URL
        self.tournament_id = SmashGGScraper.get_tournament_phase_id_from_url(self.path)
        self.event_id = SmashGGScraper.get_tournament_event_id_from_url(self.path)
        self.name = SmashGGScraper.get_tournament_name_from_url(self.path)

        #DEFINE OUR TARGET URL ENDPOINT FOR THE SMASHGG API
        #AND INSTANTIATE THE DICTIONARY THAT HOLDS THE RAW
        # JSON DUMPED FROM THE API
        base_url = TOURNAMENT_URL % self.tournament_id
        self.apiurl = base_url + DUMP_SETTINGS_ALL
        self.raw_dict = None

        #DATA STRUCTURES THAT HOLD IMPORTANT THINGS
        self.phase_ids = []
        self.pools = []
        self.players = []

        #SETUP LOGGING FILE FOR THIS IMPORT
        log_dir = Log.get_log_dir()
        t_log_dir = os.path.abspath(log_dir + os.sep + 'tournamentScrapes')
        if not os.path.isdir(log_dir):
            os.makedirs(log_dir)
        if not os.path.isdir(t_log_dir):
            os.makedirs(t_log_dir)
        self.log = Log(t_log_dir, self.name + '.log')
        self.log.write("SmashGG Scrape: " + self.name)


        #GET THE RAW JSON AT THE END OF THE CONSTRUCTOR
        self.get_raw()

######### START OF SCRAPER API

    def get_raw(self):
        """
        :return: the JSON dump that the api call returns
        """
        if self.raw_dict == None:
            self.raw_dict = {}
            self.log('API Call to ' + str(self.apiurl) + ' executing')
            self.raw_dict['smashgg'] = self._check_for_200(requests.get(self.apiurl)).json()
        return self.raw_dict

    def get_name(self):
        return self.name

    # The JSON scrape doesn't give us the Date of the tournament currently
    # Get date from earliest start time of a set
    def get_date(self):
        sets = self.get_raw()['smashgg']['entities']['sets']
        start_times = [t['startedAt'] for t in sets if t['startedAt']]

        if not start_times:
            return None
        else:
            return datetime.datetime.fromtimestamp(min(start_times))

    def get_matches(self):
        """
        :return: the list of MatchResult objects that represents every match
        played in the given bracket, including who won and who lost
        """
        matches = []
        sets = self.get_raw()['smashgg']['entities']['sets']
        for set in sets:
            winner_id = set['winnerId']
            loser_id = set['loserId']
            # CHECK FOR A BYE
            if loser_id is None:
                continue

            winner = self.get_player_by_entrant_id(winner_id)
            loser = self.get_player_by_entrant_id(loser_id)

            match = MatchResult(winner.smash_tag, loser.smash_tag)
            matches.append(match)

        # RECURSIVELY DIG AND RETRIEVE MATCHES FROM OTHER PHASES
        # WE ONLY WANT TO FETCH POOLS OF THE TOP BRACKET OTHERWISE
        # WE GET CAUGHT IN INFINITE RECURSION
        if self.is_pool is False:
            if len(self.pools) is 0:
                self.get_pools()
            for pool in self.pools:
                #CONDITION TO PREVENT DOUBLE COUNTING MATCHES
                if pool.tournament_id == self.tournament_id:
                    continue

                pool_matches = pool.get_matches()
                for match in pool_matches:
                    matches.append(match)

        return matches

####### END OF SCRAPER API


    def get_player_by_entrant_id(self, id):
        """
        :param id: id of the entrant for the current tournament
        :return: a SmashGGPlayer object that belongs to the given tournament entrant number
        """
        if self.players is None or len(self.players) == 0:
            self.get_smashgg_players()

        for player in self.players:
            if id == int(player.entrant_id):
                return player

    def get_player_by_smashgg_id(self, id):
        """
        :param id: id of the smashGG  player's account
        :return: a SmashGGPlayer object that belongs to the given smashgg id number
        """
        if self.players is None or len(self.players) == 0:
            self.get_smashgg_players()

        for player in self.players:
            if id == int(player.smashgg_id):
                return player

    def get_players(self):
        """
        :return: the smash tags of every player who is in the given bracket
        """
        if self.players is None or len(self.players) == 0:
            self.get_smashgg_players()

        tags = []
        for player in self.players:
            tags.append(str(player.smash_tag).strip())
        return tags

    def get_smashgg_players(self):
        """
        :return: and edit the local list of SmashGGPlayer objects that encapsulate important information about
        the participants of the tournament, including their name, region, smashtag,
        tournament entrant id, and overall smashgg id
        """
        self.players = []
        entrants = self.get_raw()['smashgg']['entities']['entrants']
        for player in entrants:
            tag             = None
            name            = None
            state           = None
            country         = None
            region          = None
            entrant_id      = None
            smashgg_id      = None
            final_placement = None

            try:
                #ACCESS PLAYER ID's AND INFORMATION
                entrant_id = player['id']
                for e_id, p_id in player['playerIds'].items():
                    smashgg_id = p_id
            except Exception as ex:
                self.log.write(str(e))

            for this_player in player['mutations']['players']:
                #ACCESS THE PLAYERS IN THE JSON AND EXTRACT THE SMASHTAG
                #IF NO SMASHTAG, WE SHOULD SKIP TO THE NEXT ITERATION
                try:
                    tag = player['mutations']['players'][this_player]['gamerTag'].strip()
                except Exception as ex:
                    self.log.write('Player for id ' + str(id) + ' not found')
                    continue

                #EXTRACT EXTRA DATA FROM SMASHGG WE MAY WANT TO USE LATER
                #ENCAPSULATE IN A SMASHGG SPECIFIC MODEL
                try:
                    name = player['mutations']['players'][this_player]['name'].strip()
                except Exception as e:
                    name = None
                    self.log.write('SmashGGPlayer ' + tag + ': name | ' + str(e))

                try:
                    region = player['mutations']['players'][this_player]['region'].strip()
                except Exception as regionEx:
                    self.log.write('SmashGGPlayer ' + tag + ': region | ' + str(regionEx))

                try:
                    state = player['mutations']['players'][this_player]['state'].strip()
                    if region is None:
                        region = state
                except Exception as stateEx:
                    self.log.write('SmashGGPlayer ' + tag + ': state | ' + str(stateEx))

                try:
                    country = player['mutations']['players'][this_player]['country'].strip()
                    if region is None:
                        region = country
                except Exception as countryEx:
                    self.log.write('SmashGGPlayer ' + tag + ': country | ' + str(countryEx))

                try:
                    final_placement = player['finalPlacement']
                except Exception as ex:
                    self.log.write('SmashGGPlayer ' + tag + ': final placement | ' + str(ex))

            player = SmashGGPlayer(smashgg_id=smashgg_id, entrant_id=entrant_id, name=name, smash_tag=tag, region=region,
                                   state=state, country=country, final_placement=final_placement)
            self.players.append(player)
        return self.players

    def get_smashgg_matches(self):
        """
        :return: a list of SmashGGMatch objects that encapsulate more data about the match
        than just the winner and loser. Could be useful for additional ranking metrics
        like how far into the tournament or how many matches were played.
        """
        matches = []
        sets = self.get_raw()['smashgg']['entities']['sets']
        for set in sets:
            winner_id = set['winnerId']
            loser_id = set['loserId']
            # CHECK FOR A BYE
            if loser_id is None:
                continue

            try:
                name = set['fullRoundText']
                round = set['round']
                bestOf = set['bestOf']
            except:
                self.log.write('Could not find extra details for match')
                round = None
                bestOf = None

            match = SmashGGMatch(name, winner_id, loser_id, round, bestOf)
            matches.append(match)
        # RECURSIVELY DIG AND RETRIEVE MATCHES FROM OTHER PHASES
        # WE ONLY WANT TO FETCH POOLS OF THE TOP BRACKET OTHERWISE
        # WE GET CAUGHT IN INFINITE RECURSION
        if self.is_pool is False:
            if len(self.pools) is 0:
                self.get_pools()
            for pool in self.pools:
                # CONDITION TO PREVENT DOUBLE COUNTING MATCHES
                if pool.tournament_id == self.tournament_id:
                    continue

                pool_matches = pool.get_smashgg_matches()
                for match in pool_matches:
                    matches.append(match)
        return matches

    def get_pool_by_phase_id(self, id):
        if id is None:
            pass
        pool_url = BASE_SMASHGG_PHASE_API_URL + str(id)
        pool = SmashGGScraper(pool_url)
        pool.is_pool = True
        self.pools.append(pool)

    def get_pools(self):
        if self.raw_dict is None:
            self.raw_dict = self.get_raw()
        if len(self.phase_ids) is 0:
            self.phase_ids = self.get_phase_ids()

        for id in self.phase_ids:
            if id is None:
                continue
            pool_url = BASE_SMASHGG_PHASE_API_URL + str(id)
            pool = SmashGGScraper(pool_url)
            pool.is_pool = True
            self.pools.append(pool)
        return self.pools

    def _check_for_200(self, response):
        """
        :param response: http response to check for correct http code
        :return: the body response from a successful http call
        """
        response.raise_for_status()
        return response

    def log(self, msg):
        """
        :param msg: error or log message to print or write
        :return: a string that can be used for logging
        """
        return "    [SmashGG] " + msg

    def remove_list_repeats(self, list):
        temp = []
        for item in list:
            if item not in temp:
                temp.append(item)
        return temp

    def get_groups(self, raw):
        groups = raw['entities']['groups']
        return groups

    def get_phase_ids(self):
        phase_ids = []
        event_id = SmashGGScraper.get_tournament_event_id_from_url(self.path)
        event_url = BASE_SMASHGG_EVENT_API_URL + str(event_id) + DUMP_SETTINGS_GROUPS

        event_raw = self._check_for_200(requests.get(event_url)).json()
        groups = self.get_groups(event_raw)
        for group in groups:
            #EACH ID REPRESENTS A POOL
            phase_ids.append(str(group['id']).strip())
        return self.remove_list_repeats(phase_ids)

    @staticmethod
    def get_tournament_event_id_from_url(url):
        splits = url.split('/')

        flag = False
        for split in splits:
            #IF THIS IS TRUE WE HAVE REACHED THE EVENT ID
            if flag is True:
                return int(split)

            #SET FLAG TRUE IF CURRENT WORD IS 'BRACKETS'
            #THE NEXT ELEMENT WILL BE OUR EVENT ID
            if 'brackets' in split:
                flag = True

    @staticmethod
    def get_tournament_phase_id_from_url(url):
        """
        Parses a url and retrieves the unique id of the bracket in question
        :param url: url to parse the tournament id from
        :return: the unique id of the bracket in question
        """
        id = url[url.rfind('/') + 1:]
        return int(id)

    @staticmethod
    def get_tournament_name_from_url(url):
        """
        Parses a url and retrieves the name of the tournament in question
        :param url: url to parse the tournament name from
        :return: the name of the tournament in question
        """
        tStr = 'tournament/'
        startIndex = url.rfind(tStr) + len(tStr)
        name = url[startIndex: url.index('/', startIndex)]
        return name.replace('-', ' ')

class SmashGGPlayer(object):
    def __init__(self, smashgg_id, entrant_id, name, smash_tag, region, country, state, final_placement):
        """
        :param smashgg_id:      The Global id that a player is mapped to on the website
        :param entrant_id:      The id assigned to an entrant for the given tournament
        :param name:            The real name of the player
        :param smash_tag:       The Smash Tag of the player
        :param region:          The region the player belongs to
        :param country:
        :param state:
        :param final_placement:
        """
        self.smashgg_id = smashgg_id
        self.entrant_id = entrant_id
        self.name = name
        self.smash_tag = smash_tag
        self.region = region
        self.country = country
        self.state = state

class SmashGGMatch(object):
    def __init__(self, roundName, winner_id, loser_id, roundNumber, bestOf):
        """
        :param winner_id: Entrant id of the winner of the match
        :param loser_id:  Entrant id of the loser of the match
        :param round:     Round of the bracket this match took place
        :param bestOf:    Best of this many matches
        """
        self.roundName = roundName
        self.winner_id = winner_id
        self.loser_id = loser_id
        self.roundNumber = roundNumber
        self.bestOf = bestOf

class SmashGGException(Exception):
    def __init__(self, message):
        self.message = message
