"""
awslimitchecker/services/ec2.py

The latest version of this package is available at:
<https://github.com/jantman/awslimitchecker>

################################################################################
Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>

    This file is part of awslimitchecker, also known as awslimitchecker.

    awslimitchecker is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    awslimitchecker is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with awslimitchecker.  If not, see <http://www.gnu.org/licenses/>.

The Copyright and Authors attributions contained herein may not be removed or
otherwise altered, except to add the Author attribution of a contributor to
this work. (Additional Terms pursuant to Section 7b of the AGPL v3)
################################################################################
While not legally required, I sincerely request that anyone who finds
bugs please submit them at <https://github.com/jantman/pydnstest> or
to me via email, and that you send any contributions or improvements
either as a pull request on GitHub, or to me via email.
################################################################################

AUTHORS:
Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
################################################################################
"""

import abc  # noqa
import boto
import logging
from .base import AwsService
from ..limit import AwsLimit
logger = logging.getLogger(__name__)


class Ec2Service(AwsService):

    service_name = 'EC2'

    def connect(self):
        if self.conn is None:
            logger.debug("Connecting to EC2")
            self.conn = boto.connect_ec2()
            logger.info("Connected to EC2")

    def check_usage(self):
        """
        Check this service for the usage of each resource with a known limit.
        This updates limits in self.limits.
        """
        logger.debug("Checking usage for service {n}".format(
            n=self.service_name))
        self.connect()
        # On-Demand instances by type
        ondemand = {k: 0 for k in self._instance_types()}
        for res in self.conn.get_all_reservations():
            for inst in res.instances:
                if inst.spot_instance_request_id:
                    logger.warning("Spot instance found ({i}); awslimitchecker "
                                   "does not yet support spot "
                                   "instances.".format(i=inst.id))
                    continue
                key = 'Running On-Demand {t} instances'.format(
                    t=inst.instance_type)
                ondemand[key] += 1

    def get_limits(self):
        """
        Return all known limits for this service, as a dict of their names
        to :py:class:`~.AwsLimit` objects.

        :returns: dict of limit names to :py:class:`~.AwsLimit` objects
        :rtype: dict
        """
        if self.limits is not None:
            return self.limits
        # from: http://aws.amazon.com/ec2/faqs/
        # (On-Demand, Reserved, Spot)
        default_limits = (20, 20, 5)
        special_limits = {
            'c4.4xlarge': (10, 20, 5),
            'c4.8xlarge': (5, 20, 5),
            'cg1.4xlarge': (2, 20, 5),
            'hi1.4xlarge': (2, 20, 5),
            'hs1.8xlarge': (2, 20, 0),
            'cr1.8xlarge': (2, 20, 5),
            'g2.2xlarge': (5, 20, 5),
            'g2.8xlarge': (2, 20, 5),
            'r3.4xlarge': (10, 20, 5),
            'r3.8xlarge': (5, 20, 5),
            'i2.xlarge': (8, 20, 0),
            'i2.2xlarge': (8, 20, 0),
            'i2.4xlarge': (4, 20, 0),
            'i2.8xlarge': (2, 20, 0),
            'd2.4xlarge': (10, 20, 5),
            'd2.8xlarge': (5, 20, 5),
        }
        limits = {}
        for i_type in self._instance_types():
            key = 'Running On-Demand {t} Instances'.format(
                t=i_type)
            lim = default_limits[0]
            if i_type in special_limits:
                lim = special_limits[i_type][0]
            limits[key] = AwsLimit(
                key,
                self.service_name,
                lim,
                limit_type='On-Demand Instances',
                limit_subtype=i_type
            )
        return limits

    def _instance_types(self):
        """
        Return a list of all known EC2 instance types

        :returns: list of all valid known EC2 instance types
        :rtype: list
        """
        GENERAL_TYPES = [
            't2.micro',
            't2.small',
            't2.medium',
            'm3.medium',
            'm3.large',
            'm3.xlarge',
            'm3.2xlarge',
        ]

        MEMORY_TYPES = [
            'r3.large',
            'r3.xlarge',
            'r3.2xlarge',
            'r3.4xlarge',
            'r3.8xlarge',
        ]

        COMPUTE_TYPES = [
            'c3.large',
            'c3.xlarge',
            'c3.2xlarge',
            'c3.4xlarge',
            'c3.8xlarge',
            'c4.large',
            'c4.xlarge',
            'c4.2xlarge',
            'c4.4xlarge',
            'c4.8xlarge',
        ]

        STORAGE_TYPES = [
            'i2.xlarge',
            'i2.2xlarge',
            'i2.4xlarge',
            'i2.8xlarge',
        ]

        DENSE_STORAGE_TYPES = [
            'd2.xlarge',
            'd2.2xlarge',
            'd2.4xlarge',
            'd2.8xlarge',
        ]

        GPU_TYPES = [
            'g2.2xlarge',
            'g2.8xlarge',
        ]

        return (
            GENERAL_TYPES +
            MEMORY_TYPES +
            COMPUTE_TYPES +
            STORAGE_TYPES +
            DENSE_STORAGE_TYPES +
            GPU_TYPES
        )
