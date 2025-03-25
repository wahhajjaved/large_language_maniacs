import datetime
from sqlalchemy import func, desc, or_

from app import db, login_manager
from app.storage import (Player,
                         Team,
                         Match,
                         Event,
                         Employee,
                         Formation,
                         PlayedIn)
from app.settings import START_DAY


@login_manager.user_loader
def load_employee(employee_id):
    return db.session.query(Employee).get(int(employee_id))


def get_all_arenas(db):
    """Return list of all arenas."""
    return [i[0] for i in (db.session.query(Match.arena.distinct())
                           .all())]


def get_matches_by_day(db, day_num):
    """Return all matches scheduled for day day_num of the tournament."""
    match_date = START_DAY + datetime.timedelta(day_num - 1)
    next_day = (match_date + datetime.timedelta(1)).replace(hour=0, minute=0)
    return (db.session.query(Match)
                      .filter(Match.datetime >= match_date)
                      .filter(Match.datetime < next_day)
                      .all())


def get_matches_for_arena_by_day(db, arena, day_num):
    """Return all matches scheduled for day day_num inspecific arena."""
    match_date = START_DAY + datetime.timedelta(day_num - 1)
    next_day = (match_date + datetime.timedelta(1)).replace(hour=0, minute=0)
    return (db.session.query(Match)
                      .filter_by(arena=arena)
                      .filter(Match.datetime >= match_date)
                      .filter(Match.datetime < next_day)
                      .all())


def get_player_by_surname(db, player_surname):
    """Return list of Player objects matching surname regex."""
    return (db.session.query(Player)
                      .filter_by(surname=player_surname)
                      .first())


def get_player_by_surname_regex(db, player_surname):
    """Return list of Player objects matching surname regex."""
    return (db.session.query(Player)
                      .filter(Player.surname.like('%' + player_surname + '%'))
                      .all())


def get_teams(db):
    """Return list of all Teams."""
    return (db.session.query(Team)
                      .all())


def get_team_by_name(db, team_name):
    """Return first Team object matching team_name."""
    return (db.session.query(Team)
                      .filter_by(name=team_name)
                      .first())


def get_players_from_team(db, team_name):
    """Return all players of team."""
    t = get_team_by_name(db, team_name)
    if t is not None:
        return (db.session.query(Player)
                          .filter_by(team=t)
                          .all())
    return None


def get_score(db, m, home=True):
    """Return score of home team in match m if home is true,
    score of away team otherwise."""
    attr = 'home_team' if home else 'away_team'
    return (db.session.query(Event)
                      .filter_by(match=m)
                      .filter_by(team=getattr(m, attr))
                      .filter_by(code='goal')
                      .count())


def get_most_productive(db):
    """Return ordered list of the most productive players."""
    return (db.session.query(Player, func.count(Player.events))
                      .join(Event)
                      .filter(or_(Event.code == 'goal', Event.code == 'assist'))
                      .group_by(Player)
                      .order_by(desc(func.count(Player.events)))
                      .all())


def get_num_of(db, player, what):
    """Return number of events of type what for selected player."""
    return (db.session.query(Event)
                      .filter_by(code=what)
                      .filter_by(player=player)
                      .count())


def get_num_of_games(db, player):
    """Return number of games selected player participated in."""
    return (db.session.query(Formation)
                      .join(PlayedIn)
                      .filter(PlayedIn.player == player)
                      .distinct(Formation.match_id)
                      .count())
