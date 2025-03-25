from enum import Enum

from . import model

# fake in-memory storage
ROLES = {}
ROUTES = {}
STATIONS = {}
TEAMS = {}
USERS = {}

USER_STATION_MAP = {}
TEAM_ROUTE_MAP = {}
USER_ROLES = {}
ROUTE_STATION_MAP = {}
TEAM_STATION_MAP = {}


class TeamState(Enum):
    UNKNOWN = 'unknown'
    ARRIVED = 'arrived'
    FINISHED = 'finished'


def make_default_team_state():
    return {
        'state': TeamState.UNKNOWN
    }


class Team:

    @staticmethod
    def all():
        for team in TEAMS.values():
            yield team

    @staticmethod
    def by_route(route_name):
        for team_name, team_route_name in TEAM_ROUTE_MAP.items():
            if team_route_name == route_name:
                yield team_name

    @staticmethod
    def quickfilter_unassigned():
        assigned = set(TEAM_ROUTE_MAP.keys())
        for team in Team.all():
            if team.name not in assigned:
                yield team

    @staticmethod
    def assigned_to_station(station_name):
        for team_name, _station_name in TEAM_ROUTE_MAP.items():
            if station_name == _station_name:
                yield TEAMS[team_name]

    @staticmethod
    def create_new(data):
        team = model.Team()
        team.update(**data)
        TEAMS[data['name']] = team
        return team

    @staticmethod
    def upsert(name, data):
        team = TEAMS.get(name, model.Team())
        team.update(**data)
        return team

    @staticmethod
    def delete(name):
        if name in TEAMS:
            del(TEAMS[name])
        return None

    @staticmethod
    def get_station_data(team_name, station_name):
        state = TEAM_STATION_MAP.get(team_name, {}).get(station_name, {})
        state = state or make_default_team_state()
        return state

    def advance_on_station(team_name, station_name):
        state = TEAM_STATION_MAP.get(team_name, {}).get(station_name, {})
        state = state or make_default_team_state()
        if state['state'] == TeamState.UNKNOWN:
            new_state = TeamState.ARRIVED
        elif state['state'] == TeamState.ARRIVED:
            new_state = TeamState.FINISHED
        else:
            new_state = TeamState.UNKNOWN
        return new_state


class Station:

    @staticmethod
    def all():
        for station in STATIONS.values():
            yield station

    @staticmethod
    def create_new(data):
        station = model.Station()
        station.update(**data)
        STATIONS[data['name']] = station
        return station

    @staticmethod
    def upsert(name, data):
        station = STATIONS.get(name, model.Station())
        station.update(**data)
        return station

    @staticmethod
    def delete(name):
        if name in STATIONS:
            del(STATIONS[name])
        return None

    @staticmethod
    def assign_user(station_name, user_name):
        '''
        Returns true if the operation worked, false if the use is already
        assigned to another station.
        '''
        assigned_station = USER_STATION_MAP.get(user_name)
        if assigned_station:
            return False
        USER_STATION_MAP[user_name] = station_name
        return True

    @staticmethod
    def unassign_user(station_name, user_name):
        if station_name in USER_STATION_MAP:
            del(USER_STATION_MAP[station_name])
        return True


class Route:

    @staticmethod
    def all():
        for station in ROUTES.values():
            yield station

    @staticmethod
    def create_new(data):
        route = model.Route()
        route.update(**data)
        ROUTES[data['name']] = route
        return route

    @staticmethod
    def upsert(name, data):
        route = ROUTES.get(name, model.Route())
        route.update(**data)
        return route

    @staticmethod
    def delete(name):
        if name in ROUTES:
            del(ROUTES[name])
        return None

    @staticmethod
    def assign_team(route_name, team_name):
        assigned_route = TEAM_ROUTE_MAP.get(team_name)
        if assigned_route:
            return False
        TEAM_ROUTE_MAP[team_name] = route_name
        return True

    @staticmethod
    def unassign_team(route_name, team_name):
        if team_name in TEAM_ROUTE_MAP:
            del(TEAM_ROUTE_MAP[team_name])
        return True

    @staticmethod
    def assign_station(route_name, station_name):
        assigned_routes = ROUTE_STATION_MAP.get(station_name, set())
        assigned_routes.add(route_name)
        return True

    @staticmethod
    def unassign_station(route_name, station_name):
        assigned_routes = ROUTE_STATION_MAP.get(station_name, set())
        if route_name in assigned_routes:
            assigned_routes.remove(route_name)
        return True


class User:

    @staticmethod
    def assign_role(user_name, role_name):
        assigned_roles = USER_ROLES.get(user_name, set())
        assigned_roles.add(role_name)
        return True

    @staticmethod
    def unassign_role(user_name, role_name):
        roles = USER_ROLES.get(user_name, set())
        if role_name in roles:
            roles.remove(role_name)
        return True
