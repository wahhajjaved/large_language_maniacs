# The Hazard Library
# Copyright (C) 2012-2014, GEM Foundation
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import functools
import pickle

from openquake.hazardlib import speedups


def assert_angles_equal(testcase, angle1, angle2, delta):
    if abs(angle1 - angle2) > 180:
        angle1, angle2 = 360 - max((angle1, angle2)), min((angle1, angle2))
    testcase.assertAlmostEqual(angle1, angle2, delta=delta)


def assert_pickleable(obj):
    pickle.loads(pickle.dumps(obj)).assert_equal(obj)


def speedups_on_off(cls):
    """
    For all the test case methods in the class creates a copy with
    "_no_speedups" suffix in the name, where runs the same test case
    but with speedups disabled.
    """

    def make_no_speedups_on_off(method):
        @functools.wraps(method)
        def method2(*args, **kwargs):
            speedups.disable()
            try:
                method(*args, **kwargs)
            finally:
                speedups.enable()
        return method2

    for name, member in vars(cls).items():
        if not name.startswith('test_'):
            continue
        if not callable(member):
            continue
        name = '%s_no_speedups' % name
        setattr(cls, name, make_no_speedups_on_off(member))

    return cls
