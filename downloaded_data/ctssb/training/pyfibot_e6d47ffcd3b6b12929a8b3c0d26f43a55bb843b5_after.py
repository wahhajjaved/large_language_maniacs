#!/usr/bin/python
"""
Fetch series data from thetvdb.com via their API
Displays next episode if one exists, previous if no future episodes are known
"""

from __future__ import unicode_literals, print_function, division
from datetime import datetime, timedelta

api_ok = True
try:
    import tvdb_api
    import tvdb_exceptions
except:
    print("tvdb api not available")
    api_ok = False
from operator import itemgetter


def command_ep(bot, user, channel, args):
    """Usage: ep <series name>"""
    if not api_ok:
        return
    t = tvdb_api.Tvdb()
    now = datetime.now()
    # one day resolution maximum
    now = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # prevent "Series '' not found"
    if not args:
        return

    try:
        series = t[args]
    except tvdb_exceptions.tvdb_shownotfound:
        bot.say(channel, "Series '%s' not found" % args)
        return

    future_episodes = []
    all_episodes = []

    # find all episodes with airdate > now
    for season_no, season in series.items():
        for episode_no, episode in season.items():
            firstaired = episode['firstaired']
            if not firstaired:
                continue
            airdate = datetime.strptime(firstaired, "%Y-%m-%d")
            td = airdate - now

            all_episodes.append(episode)
            # list all unaired episodes
            if td >= timedelta(0, 0, 0):
                future_episodes.append(episode)

    # if any future episodes were found, find out the one with airdate closest to now
    if future_episodes:
        # sort the list just in case it's out of order (specials are season 0)
        future_episodes = sorted(future_episodes, key=itemgetter('firstaired'))
        episode = future_episodes[0]
        td = datetime.strptime(episode['firstaired'], "%Y-%m-%d") - now

        if td.days == 1:
            airdate = "tomorrow"
        elif td.days > 1:
            airdate = "%s (%d days)" % (episode['firstaired'], td.days)
        else:
            airdate = "today"

        season_ep = "%dx%02d" % (int(float(episode['combined_season'])),int(float(episode['combined_episodenumber'])))
        msg = "Next episode of %s %s '%s' airs %s" % (series.data['seriesname'], season_ep, episode['episodename'], airdate)
    # no future episodes found, show the latest one
    elif all_episodes:
        # find latest episode of the show
        all_episodes = sorted(all_episodes, key=itemgetter('firstaired'))
        episode = all_episodes[-1]

        ## episode age in years and days
        td = now - datetime.strptime(episode['firstaired'], "%Y-%m-%d")
        years, days = td.days // 365, td.days % 365
        agestr = []
        if years >= 1:
            agestr.append("%d years" % years)
        if days > 0:
            agestr.append("%d days" % days)

        airdate = "%s (%s ago)" % (episode['firstaired'], " ".join(agestr))

        season_no = int(episode['combined_season'])
        # the episode number is sometimes returned as a float, hack it.
        episode_no = int(float(episode['combined_episodenumber']))

        season_ep = "%dx%02d" % (season_no, episode_no)
        msg = "Latest episode of %s %s '%s' aired %s" % (series.data['seriesname'], season_ep, episode['episodename'], airdate)
    else:
        msg = "No new or past episode airdates found for %s" % series.data['seriesname']

    bot.say(channel, msg.encode("UTF-8"))
