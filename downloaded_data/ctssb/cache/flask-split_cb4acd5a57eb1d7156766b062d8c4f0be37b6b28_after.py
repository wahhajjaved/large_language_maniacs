# -*- coding: utf-8 -*-
"""
    flask.ext.split.models
    ~~~~~~~~~~~~~~~~~~~~~~

    This module provides the models for experiments and alternatives.

    :copyright: (c) 2012 by Janne Vanhala.
    :license: MIT, see LICENSE for more details.
"""

from datetime import datetime
from math import sqrt
from random import random
from collections import defaultdict


class Alternative(object):
    def __init__(self, redis, name, experiment_name):
        self.redis = redis
        self.experiment_name = experiment_name
        if isinstance(name, tuple):
            self.name, self.weight = name
        else:
            self.name = name
            self.weight = 1

    def _get_participant_count(self):
        return int(self.redis.hget(self.key, 'participant_count') or 0)

    def _set_participant_count(self, count):
        self.redis.hset(self.key, 'participant_count', int(count))

    participant_count = property(
        _get_participant_count,
        _set_participant_count
    )

    def _get_completed_count(self):
        return int(self.redis.hget(self.key, 'completed_count') or 0)

    def _set_completed_count(self, count):
        self.redis.hset(self.key, 'completed_count', int(count))

    completed_count = property(
        _get_completed_count,
        _set_completed_count
    )

    def increment_participation(self):
        self.redis.hincrby(self.key, 'participant_count', 1)

    def increment_completion(self):
        self.redis.hincrby(self.key, 'completed_count', 1)

    @property
    def is_control(self):
        return self.experiment.control.name == self.name

    @property
    def conversion_rate(self):
        if self.participant_count == 0:
            return 0
        return float(self.completed_count) / float(self.participant_count)

    @property
    def experiment(self):
        return Experiment.find(self.redis, self.experiment_name)

    def save(self):
        self.redis.hsetnx(self.key, 'participant_count', 0)
        self.redis.hsetnx(self.key, 'completed_count', 0)

    def reset(self):
        self.redis.hmset(self.key, {
            'participant_count': 0,
            'completed_count': 0
        })

    def delete(self):
        self.redis.delete(self.key)

    @property
    def key(self):
        return '%s:%s' % (self.experiment_name, self.name)

    @property
    def z_score(self):
        control = self.experiment.control
        alternative = self

        if control.name == alternative.name:
            return None

        cr = alternative.conversion_rate
        crc = control.conversion_rate

        n = alternative.participant_count
        nc = control.participant_count

        if n == 0 or nc == 0:
            return None

        mean = cr - crc
        var_cr = cr * (1 - cr) / float(n)
        var_crc = crc * (1 - crc) / float(nc)

        if var_cr + var_crc <= 0:
            return None

        return mean / sqrt(var_cr + var_crc)

    @property
    def confidence_level(self):
        z = self.z_score
        if z is None:
            return 'N/A'
        z = abs(round(z, 3))
        if z == 0:
            return 'no change'
        elif z < 1.64:
            return 'no confidence'
        elif z < 1.96:
            return '90% confidence'
        elif z < 2.57:
            return '95% confidence'
        elif z < 3.29:
            return '99% confidence'
        else:
            return '99.9% confidence'


class Experiment(object):
    def __init__(self, redis, name, group, *alternative_names):
        self.redis = redis
        self.name = name
        self.group = group
        if self.group:
            redis.set(Experiment.group_name_redis_key(name), group)
        self.alternatives = [
            Alternative(redis, alternative, name)
            for alternative in alternative_names
        ]

    @property
    def control(self):
        return self.alternatives[0]

    def _get_winner(self):
        winner = self.redis.hget('experiment_winner', self.name)
        if winner:
            winner = unicode(winner, 'utf-8')
            return Alternative(self.redis, winner, self.name)

    def _set_winner(self, winner_name):
        self.redis.hset('experiment_winner', self.name, winner_name)

    winner = property(
        _get_winner,
        _set_winner
    )

    def reset_winner(self):
        """Reset the winner of this experiment."""
        self.redis.hdel('experiment_winner', self.name)

    @property
    def start_time(self):
        """The start time of this experiment."""
        t = self.redis.hget('experiment_start_times', self.name)
        return datetime.strptime(t, '%Y-%m-%dT%H:%M:%S') if t else datetime.now()

    @property
    def total_participants(self):
        """The total number of participants in this experiment."""
        return sum(a.participant_count for a in self.alternatives)

    @property
    def total_completed(self):
        """The total number of users who completed this experiment."""
        return sum(a.completed_count for a in self.alternatives)

    @property
    def alternative_names(self):
        """A list of alternative names. in this experiment."""
        return [alternative.name for alternative in self.alternatives]

    def next_alternative(self):
        """Return the winner of the experiment if set, or a random
        alternative."""
        return self.winner or self.random_alternative()

    def random_alternative(self):
        total = sum(alternative.weight for alternative in self.alternatives)
        point = random() * total
        for alternative in self.alternatives:
            if alternative.weight >= point:
                return alternative
            point -= alternative.weight

    @property
    def version(self):
        return int(self.redis.get('%s:version' % self.name) or 0)

    def increment_version(self):
        self.redis.incr('%s:version' % self.name)

    @property
    def key(self):
        if self.version > 0:
            return "%s:%s" % (self.name, self.version)
        else:
            return self.name

    def reset(self):
        """Delete all data for this experiment."""
        for alternative in self.alternatives:
            alternative.reset()
        self.reset_winner()
        self.increment_version()

    def delete(self):
        """Delete this experiment and all its data."""
        for alternative in self.alternatives:
            alternative.delete()
        self.reset_winner()
        self.redis.srem('experiments', self.name)
        self.redis.delete(self.name)
        self.increment_version()

    @property
    def is_new_record(self):
        return self.name not in self.redis

    def save(self):
        if self.is_new_record:
            start_time = self._get_time().isoformat()[:19]
            self.redis.sadd('experiments', self.name)
            self.redis.hset('experiment_start_times', self.name, start_time)
            for alternative in reversed(self.alternatives):
                self.redis.lpush(self.name, alternative.name)

    def find_or_create_alternative(self, alternative_name):
        alternative = None
        if not alternative_name in self.alternative_names:
            alternative = Alternative(self.redis, alternative_name, self.name)
            alternative._set_participant_count(0)
            alternative._set_completed_count(0)
            self.alternatives.append(alternative)
        else:
            for existing_alternative in self.alternatives:
                if existing_alternative.name == alternative_name:
                    alternative = existing_alternative
                    break
        return alternative

    @classmethod
    def load_alternatives_for(cls, redis, name):
        return [unicode(a, 'utf-8') for a in redis.lrange(name, 0, -1)]

    @classmethod
    def all(cls, redis):
        return [cls.find(redis, unicode(e, 'utf-8')) for e in redis.smembers('experiments')]

    @classmethod
    def find(cls, redis, name):
        if name in redis:
            group = redis.get(cls.group_name_redis_key(name))
            return cls(redis, name, group, *cls.load_alternatives_for(redis, name))

    @classmethod
    def find_or_create(cls, redis, key, group, *alternatives):
        name = key.split(':')[0]

        if len(alternatives) < 2:
            raise TypeError('You must declare at least 2 alternatives.')

        experiment = cls.find(redis, name)
        if experiment:
            alts = [a[0] if isinstance(a, tuple) else a for a in alternatives]
            if [a.name for a in experiment.alternatives] != alts:
                experiment.reset()
                for alternative in experiment.alternatives:
                    alternative.delete()
                experiment = cls(redis, name, group, *alternatives)
                experiment.save()
        else:
            experiment = cls(redis, name, group, *alternatives)
            experiment.save()
        return experiment


    @classmethod
    def group_name_redis_key(cls, name):
        return name + '_group' 


    @classmethod
    def get_grouped_results(cls, redis, experiments):
        groups = defaultdict(lambda: None)
        for experiment in experiments:
            if experiment.group:
                grouped_results = groups[experiment.group]
                if not grouped_results:
                    grouped_results = Experiment(redis, experiment.group + '_Totals', experiment.group)
                    groups.update({ experiment.group :  grouped_results })
                for alternative in experiment.alternatives:
                    alternative_sum = grouped_results.find_or_create_alternative(alternative.name)
                    alternative_sum._set_participant_count(alternative_sum._get_participant_count()+alternative._get_participant_count())
                    alternative_sum._set_completed_count(alternative_sum._get_completed_count()+alternative._get_completed_count())
        return groups.values()

    def _get_time(self):
        return datetime.now()
