import json
import time
from uuid import uuid4

from btrc import CouchbaseClient, StatsReporter
from couchbase import Couchbase
from logger import logger

from perfrunner.settings import SF_STORAGE


class BtrcReporter(object):

    def __init__(self, test):
        self.test = test

    def reset_utilzation_stats(self):
        for target in self.test.target_iterator:
            logger.info('Resetting utilization stats from {0}/{1}'.format(
                        target.node, target.bucket))
            cb = CouchbaseClient(target.node, target.bucket)
            cb.reset_utilization_stats()

    def save_utilzation_stats(self):
        for target in self.test.target_iterator:
            logger.info('Saving utilization stats from {0}/{1}'.format(
                        target.node, target.bucket))
            cb = CouchbaseClient(target.node, target.bucket)
            reporter = StatsReporter(cb)
            reporter.report_stats('util_stats')

    def save_btree_stats(self):
        for target in self.test.target_iterator:
            logger.info('Saving B-tree stats from {0}/{1}'.format(
                        target.node, target.bucket))
            cb = CouchbaseClient(target.node, target.bucket)
            reporter = StatsReporter(cb)
            reporter.report_stats('btree_stats')


class SFReporter(object):

    def __init__(self, test):
        self.test = test

    def _add_cluster(self):
        cluster = self.test.cluster_spec.name
        params = self.test.cluster_spec.get_parameters()
        try:
            cb = Couchbase.connect(bucket='clusters', **SF_STORAGE)
            cb.set(cluster, params)
        except Exception, e:
            logger.warn('Failed to add cluster, {0}'.format(e))
        else:
            logger.info('Successfully posted: {0}, {1}'.format(
                cluster, params))

    def _add_metric(self, metric, metric_info):
        if metric_info is None:
            metric_info = {
                'title': self.test.test_config.get_test_descr(),
                'cluster': self.test.cluster_spec.name,
                'larger_is_better': self.test.test_config.get_regression_criterion()
            }
        try:
            cb = Couchbase.connect(bucket='metrics', **SF_STORAGE)
            cb.set(metric, metric_info)
        except Exception, e:
            logger.warn('Failed to add cluster, {0}'.format(e))
        else:
            logger.info('Successfully posted: {0}, {1}'.format(metric,
                                                               metric_info))

    def _prepare_data(self, metric, value):
        key = uuid4().hex
        master_node = self.test.cluster_spec.get_masters().values()[0]
        build = self.test.rest.get_version(master_node)
        data = {'build': build, 'metric': metric, 'value': value}
        return key, data

    def _mark_previous_as_obsolete(self, cb, benckmark):
        for row in cb.query('benchmarks', 'values_by_build_and_metric',
                            key=[benckmark['metric'], benckmark['build']]):
            doc = cb.get(row.docid)
            doc.value.update({'obsolete': True})
            cb.set(row.docid, doc.value)

    def _log_benchmark(self, metric, value):
        _, benckmark = self._prepare_data(metric, value)
        logger.info('Dry run stats: {0}'.format(benckmark))

    def _post_benckmark(self, metric, value):
        key, benckmark = self._prepare_data(metric, value)
        try:
            cb = Couchbase.connect(bucket='benchmarks', **SF_STORAGE)
            self._mark_previous_as_obsolete(cb, benckmark)
            cb.set(key, benckmark)
        except Exception, e:
            logger.warn('Failed to post results, {0}'.format(e))
        else:
            logger.info('Successfully posted: {0}'.format(benckmark))

    def post_to_sf(self, value, metric=None, metric_info=None):
        if metric is None:
            metric = '{0}_{1}'.format(self.test.test_config.name,
                                      self.test.cluster_spec.name)

        stats_settings = self.test.get_stats_settings()

        if stats_settings.post_to_sf:
            self._add_metric(metric, metric_info)
            self._add_cluster()
            self._post_benckmark(metric, value)
        else:
            self._log_benchmark(metric, value)


class LogReporter(object):

    def __init__(self, test):
        self.test = test

    def save_web_logs(self):
        for target in self.test.target_iterator:
            logs = self.test.rest.get_logs(target.node)
            fname = 'web_log_{0}.json'.format(target.node.split(':')[0])
            with open(fname, 'w') as fh:
                fh.write(json.dumps(logs, indent=4, sort_keys=True))

    def save_master_events(self):
        for target in self.test.target_iterator:
            master_events = self.test.rest.get_master_events(target.node)
            fname = 'master_events_{0}.log'.format(target.node.split(':')[0])
            with open(fname, 'w') as fh:
                fh.write(master_events)


class Reporter(BtrcReporter, SFReporter, LogReporter):

    def start(self):
        self.ts = time.time()

    def finish(self, action):
        elapsed = round((time.time() - self.ts) / 60, 1)
        logger.info(
            'Time taken to perform "{0}": {1} min'.format(action, elapsed)
        )
        return elapsed
