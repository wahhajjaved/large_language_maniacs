#!/usr/bin/env python
#  -*- coding: utf-8 -*-

import datetime

import boto.ec2.cloudwatch

import blackbird.plugins.base


class ConcreteJob(blackbird.plugins.base.JobBase):

    def __init__(self, options, queue=None, logger=None):
        super(ConcreteJob, self).__init__(options, queue, logger)

        self.metrics_config = [
            {'PutRecord.Bytes': 'Sum'},
            {'PutRecord.Latency': 'Average'},
            {'PutRecord.Success': 'Sum'},
            {'GetRecords.Bytes': 'Sum'},
            {'GetRecords.IteratorAgeMilliseconds': 'Average'},
            {'GetRecords.Latency': 'Average'},
            {'GetRecords.Success': 'Sum'},
        ]
        self.per_second_key_mapping = {
            'PutRecord.Bytes': 'PutRecordBytes.PerSecond',
            'PutRecord.Success': 'PutRecordSuccess.PerSecond',
            'GetRecords.Bytes': 'GetRecordsBytes.PerSecond',
            'GetRecords.Success': 'GetRecordsSuccess.PerSecond'
        }

    def _create_connection(self):
        conn = boto.ec2.cloudwatch.connect_to_region(
            region_name=self.options.get('region_name'),
            aws_access_key_id=self.options.get(
                'aws_access_key_id'
            ),
            aws_secret_access_key=self.options.get(
                'aws_secret_access_key'
            )
        )
        return conn

    def _enqueue(self, item):
        self.queue.put(item, block=False)
        self.logger.debug(
            'Inserted to queue {key}:{value}'
            ''.format(
                key=item.key,
                value=item.value
            )
        )

    def _fetch_metrics(self):
        conn = self._create_connection()
        result = dict()

        period = int(self.options.get('interval', 300))
        if period <= 300:
            period = 300
        delta_seconds = period

        end_time = datetime.datetime.utcnow()
        start_time = end_time - datetime.timedelta(
            seconds=delta_seconds
        )
        dimensions = {
            'StreamName': self.options.get('stream_name')
        }

        for entry in self.metrics_config:
            metric_name = entry.keys()[0]
            statistics = entry.values()[0]
            response = conn.get_metric_statistics(
                period=period,
                start_time=start_time,
                end_time=end_time,
                metric_name=metric_name,
                namespace='AWS/Kinesis',
                statistics=statistics,
                dimensions=dimensions,
            )
            try:
                result_key = '{0}.{1}'.format(metric_name, statistics)

                if len(response) <= 0:
                    result[result_key] = None
                else:
                    result[result_key] = (
                        response[0][statistics]
                    )

                if (
                    metric_name in self.per_second_key_mapping and
                    len(response) > 0
                ):
                    result[
                        self.per_second_key_mapping[metric_name]
                    ] = response[0][statistics] / period

            except Exception as exception:
                self.logger.error(
                    exception.__str__()
                )

        conn.close()
        return result


    def build_items(self):
        """
        Main loop.
        """
        raw_items = self._fetch_metrics()

        for key, value in raw_items.items():
            item = KinesisStreamItem(
                key=key,
                value=str(value),
                host=self.options.get('hostname')
            )
            self._enqueue(item)


class Validator(blackbird.plugins.base.ValidatorBase):
    """
    Validate configuration object.
    """

    def __init__(self):
        self.__spec = None

    @property
    def spec(self):
        self.__spec = (
            "[{0}]".format(__name__),
            "region_name = string()",
            "aws_access_key_id = string()",
            "aws_secret_access_key = string()",
            "stream_name = string()",
            "hostname = string()"
        )
        return self.__spec


class KinesisStreamItem(blackbird.plugins.base.ItemBase):
    """
    Enqueued item.
    """

    def __init__(self, key, value, host):
        super(KinesisStreamItem, self).__init__(key, value, host)

        self.__data = dict()
        self._generate()

    @property
    def data(self):
        return self.__data

    def _generate(self):
        self.__data['key'] = 'cloudwatch.kinesis.stream.{0}'.format(self.key)
        self.__data['value'] = self.value
        self.__data['host'] = self.host
        self.__data['clock'] = self.clock


if __name__ == '__main__':
    import json
    import logging
    OPTIONS = {
        'region_name': 'us-east-1',
        'aws_access_key_id': 'YOUR_AWS_ACCESS_JEY_ID',
        'aws_secret_access_key': 'YOUR_AWS_SECRET_ACCESS_KEY',
        'stream_name': 'YOUR_KINESIS_STREAM_NAME',
    }
    JOB = ConcreteJob(
        options=OPTIONS,
        logger=logging
    )
    print(json.dumps(JOB._fetch_metrics()))
