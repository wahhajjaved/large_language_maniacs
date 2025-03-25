
import sys

def report_errors(type_, id_, errors):
    if len(errors) == 0:
        return

    print >>sys.stderr, "{0} {1} has the following errors:".format(type_, id_)
    for error in errors:
        print >>sys.stderr, "    {0}".format(error)

def validate(comp):
    count = 0
    count += validate_schedule(comp.schedule, comp.teams.keys())
    count += validate_scores(comp.scores.league, comp.schedule.matches)
    return count

def validate_schedule(schedule, possible_teams):
    count = 0
    for num, match in enumerate(schedule.matches):
        errors = validate_match(match, possible_teams)
        count += len(errors)
        report_errors('Match', num, errors)

    planned = schedule.n_planned_matches
    actual = schedule.n_matches()
    if planned != actual:
        count += 1
        msg = "Only contains enough time for {0} matches, {1} are planned" \
                .format(actual, planned)
        report_errors('Schedule', '', [msg])

    return count

def validate_match(match, possible_teams):
    errors = []
    all_teams = []

    for a in match.values():
        all_teams += a.teams

    teams = set(all_teams)
    for t in teams:
        all_teams.remove(t)

    if len(all_teams):
        duplicates = ", ".join(set(all_teams))
        errors.append("Teams {0} appear more than once.".format(duplicates))

    extras = teams - set(possible_teams)

    if len(extras):
        extras = ", ".join(extras)
        errors.append("Teams {0} do not exist.".format(extras))

    return errors

def validate_scores(scores, schedule):
    # NB: more specific validation is already done during the scoring,
    # so all we need to do is check that the right teams are being awarded points

    count = 0

    def get_scheduled_match(match_id, type_):
        num = match_id[1]
        if num < 0 or num >= len(schedule):
            report_errors(type_, match_id, ['Match not scheduled'])
            return None

        arena = match_id[0]
        match = schedule[num]
        if arena not in match:
            report_errors(type_, match_id, ['Arena not in this match'])
            return None

        return match[arena]

    def check(type_, match_id, match):
        scheduled_match = get_scheduled_match(match_id, type_)
        if scheduled_match is None:
            return 1

        errors = validate_match_score(match, scheduled_match)
        report_errors(type_, match_id, errors)
        return len(errors)

    for match_id, match in scores.game_points.items():
        count += check('Game Score', match_id, match)

    for match_id, match in scores.match_league_points.items():
        count += check('League Points', match_id, match)

    return count

def validate_match_score(match_score, scheduled_match):
    expected_teams = set(scheduled_match.teams)
    actual_teams = set(match_score.keys())

    extra = actual_teams - expected_teams
    missing = expected_teams - actual_teams

    errors = []
    if len(missing):
        missing = ', '.join(missing)
        errors.append("Teams {0} missing from this match.".format(missing))

    if len(extra):
        extra = ', '.join(extra)
        errors.append("Teams {0} not scheduled in this match.".format(extra))

    return errors
