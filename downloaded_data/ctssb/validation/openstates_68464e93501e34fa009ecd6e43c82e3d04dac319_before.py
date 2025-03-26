from __future__ import with_statement
import os

try:
    import json
except ImportError:
    import simplejson as json

from fiftystates.scrape import Scraper, FiftystatesObject, JSONDateEncoder


class VoteScraper(Scraper):
    def scrape_votes(self, chamber, year):
        raise NotImplementedYear('VoteScrapers must define a '
                                 'scrape_votes method')

    def save_vote(self, vote):
        filename = vote["filename"] + ".json"
        self.log("_save_standalone_vote %s %s: %s '%s'" % (vote['session'],
                                                           vote['chamber'],
                                                           vote['bill_id'],
                                                           vote['motion']))

        path = os.path.join(self.output_dir, 'votes', filename)
        try:
            with open(path, 'w') as f:
                json.dump(vote, f, cls=JSONDateEncoder)
        except IOError as e:
            if e.errno == 2:
                os.makedirs(os.path.join(self.output_dir, 'votes'))
                with open(path, 'w') as f:
                    json.dump(vote, f, cls=JSONDateEncoder)


class Vote(FiftystatesObject):
    def __init__(self, chamber, date, motion, passed,
                 yes_count, no_count, other_count, **kwargs):
        """
        Create a new :obj:`Vote`.

        :param chamber: the chamber in which the vote was taken,
          'upper' or 'lower'
        :param date: the date/time when the vote was taken
        :param motion: a string representing the motion that was being voted on
        :param passed: did the vote pass, True or False
        :param yes_count: the number of 'yes' votes
        :param no_count: the number of 'no' votes
        :param other_count: the number of abstentions, 'present' votes,
          or anything else not covered by 'yes' or 'no'.

        Any additional keyword arguments will be associated with this
        vote and stored in the database.

        Examples: ::

          Vote('upper', '', '12/7/08', 'Final passage',
               True, 30, 8, 3)
          Vote('lower', 'Finance Committee', '3/4/03 03:40:22',
               'Recommend passage', 12, 1, 0)
        """
        super(Vote, self).__init__('vote', **kwargs)
        self['chamber'] = chamber
        self['date'] = date
        self['motion'] = motion
        self['passed'] = passed
        self['yes_count'] = yes_count
        self['no_count'] = no_count
        self['other_count'] = other_count
        self['yes_votes'] = []
        self['no_votes'] = []
        self['other_votes'] = []

    def yes(self, legislator):
        """
        Indicate that a legislator (given as a string of their name) voted
        'yes'.

        Examples: ::

           vote.yes('Smith')
           vote.yes('Alan Hoerth')
        """
        self['yes_votes'].append(legislator)

    def no(self, legislator):
        """
        Indicate that a legislator (given as a string of their name) voted
        'no'.
        """
        self['no_votes'].append(legislator)

    def other(self, legislator):
        """
        Indicate that a legislator (given as a string of their name) abstained,
        voted 'present', or made any other vote not covered by 'yes' or 'no'.
        """
        self['other_votes'].append(legislator)
