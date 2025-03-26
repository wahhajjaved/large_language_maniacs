# -*- python -*-
# ex: set syntax=python:

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import urllib

from common import cros_chromite
from master.cros import builder_config

# Load all of Chromite's 'cbuildbot' config targets from ToT.
# NOTE: This uses a pinned Chromite configuration. To update the Chromite
#       configuration and, thorugh it, the master configuration, the pinned
#       hash should be updated in "<build>/scripts/common/cros_chromite.py".
#       (See cros_chromite.PINS documentation).
# TODO(dnj): We allow fetching here because neither the CQ nor masters will run
#            `gclient runhooks` automatically. I'd prefer it not do this so
#            master restarts are deterministic and fast. However, since the
#            loaded configuration is pinned and cached, this shouldn't have a
#            significant impact in practice.
configs = cros_chromite.Get()

# Load builder sets from the 'cbuildbot' config.
cbb_builders = set(v['_template'] or k for k, v in configs.iteritems())
etc_builders = set(['etc'])
all_builders = cbb_builders.union(etc_builders)

# Build a list of configs that contain at least one non-VMTest, non-HWTest
# Pre-CQ builder. This is used for determining a list of configs that could
# theoretically run on GCE (we check this for sure in NextSlaveAndBuild).
precq_builders = set(
    v['_template'] or k for k, v in configs.iteritems() if v.IsPreCqBuilder())
precq_novmtest_builders = set(
    v['_template'] or k for k, v in configs.iteritems()
    if v.IsPreCqBuilder() and not v.HasVmTests() and not v.HasHwTests())


class TestingSlavePool(object):

  def __init__(self, testing_slaves=None):
    self.testing_slaves = set(testing_slaves or ())

  def is_testing_slave(self, slavename):
    return slavename in self.testing_slaves

  def cros_slave_name(self, slavename):
    """BuildBot Jinja2 template function to style our slave groups into pools.

    This function is called by our customized 'buildslaves.html' template. Given
    a slave name, it returns the name to display for that slave.
    """
    if self.is_testing_slave(slavename):
      return '%s (Testing)' % (slavename,)
    return slavename


def cros_builder_links_pool(name, builders):
  """Returns a builder list for a pool, summarizing multiple builders in a
  single entry (see cros_builder_links).

  Args:
    name: The name of the pool.
    builders: The builders that compose the pool.

  Returns:
    A builder list (see cros_builder_links for description).
  """

  query = '&'.join('builder=%s' % (urllib.quote(n),)
                   for n in sorted(builders))
  return [{'link': 'builders?%s' % (query,), 'name': name}]


def cros_builder_links(builders):
  """BuildBot Jinja2 template function to style our slave groups into pools.

  This function is called by our customized 'buildslaves.html' template. It is
  evaluated for each slave, receiving 'builders', a list containing template
  information for each builder attached to that slave.

  This function accepts and returns a list containing entries:
    {'name': <name>, 'link': <link>}

  Each entry is then used by the templating engine to populate that slave's
  builder table cell. This function analyzes the list of builders for a
  given slave and optionally returns a modified set of links to render.

  This function summarizes known sets of builders, replacing individual builder
  names/links with concise builder pool names/links.
  """
  builder_names = set(s['name'] for s in builders)

  if builder_names == all_builders:
    return [{'link': 'builders', 'name': 'General'}]
  elif builder_names == precq_builders:
    return cros_builder_links_pool('Pre-CQ', precq_builders)
  elif builder_names == precq_novmtest_builders:
    return cros_builder_links_pool('Pre-CQ (GCE)',
                                   precq_novmtest_builders)
  return builders


class NextSlaveAndBuild(object):
  """Callable BuildBot 'nextSlaveAndBuild' function for ChromeOS try server.

  This function differs from default assignment:
  - It preferentially assigns slaves to builds that explicitly request slaves.
  - It prioritizes higher-strata builders when multiple builders are asking
    for slaves.
  - It prioritizes slaves with fewer builders (more specialized) over slaves
    with more builders.
  """

  def __init__(self, testing_slave_pool=None):
    """Initializes a new callable object.

    Args:
      testing_slave_pool (None/TestingSlavePool): If not None, the pool of
          testing slaves.
    """
    self.testing_slave_pool = testing_slave_pool or TestingSlavePool()

  @staticmethod
  def get_buildrequest_category(br):
    """Returns (str): the category of builder associated with a build request.
    """
    builder = br.master.status.getBuilder(br.buildername)
    if not builder:
      return None
    return builder.category

  # Paraphrased from 'buildbot.status.web.slaves.content()'.
  @staticmethod
  def get_slave_builders(slave, br):
    """Returns (list): The names (str) of builders assigned to a slave.
    """
    builders = []
    for bname in br.master.status.getBuilderNames():
      b = br.master.status.getBuilder(bname)
      for bs in b.getSlaves():
        if bs.getName() == slave.slavename:
          builders.append(b)
    return builders

  def is_testing_slave(self, slave):
    """Returns: True if 'slave' is a testing slave.

    Args:
      slave (BuildSlave): The build slave to test.
    """
    return self.testing_slave_pool.is_testing_slave(slave.slavename)

  def FilterSlaves(self, chromeos_config, slaves):
    """Filters |slaves| to only contain valid slaves for |chromeos_config|.

    Args:
      chromeos_config (ChromiteTarget): The config to filter for.
      slaves: List of BuildSlave objects to filter to filter.
    """
    if (not chromeos_config or chromeos_config.HasVmTests() or
        chromeos_config.HasHwTests()):
      slaves = [s for s in slaves if not builder_config.IsGCESlave(s.getName())]
    return slaves

  def __call__(self, slaves, buildrequests):
    """Called by master to determine which job to run and which slave to use.

    Build requests may have a 'slaves_request' property (list of strings),
    established from the try job definition. Such requests allow try jobs to
    request to be run on specific slaves.

    Arguments:
      slaves: A list of candidate SlaveBuilder objects.
      buildrequests: A list of pending BuildRequest objects.

    Returns:
      A (slave, buildrequest) tuple containing the buildrequest to run and
      the slave to run it on.
    """
    # We need to return back a BuilderSlave object, so map slave names to
    # BuilderSlave objects.
    slave_dict = dict((bs.slave.slavename, bs) for bs in slaves)

    # Service builds with explicit slave requests first. A build requesting a
    # specific set of slaves will only be scheduled on those slaves.
    remaining = []
    for br in buildrequests:
      slaves_request = br.properties.getProperty('slaves_request', None)
      if not slaves_request:
        remaining.append(br)
        continue

      # If a list of slaves are requested, the order of the list is the order
      # of preference.
      for slave_name in slaves_request:
        s = slave_dict.get(slave_name)
        if s:
          return s, br

    # Service builds based on priority. We will use a builder's 'category' as
    # its priority, which also mirrors waterfall ordering.
    #
    # Note: Python sort is stable, so this will preserve the relative order of
    # build requests that share a category.
    remaining.sort(key=self.get_buildrequest_category)

    # Get a list of available slaves. We'll sort ascendingly by number of
    # attached builders with the intention of using more-specialized (fewer
    # attached builders) slaves before using generic ones.
    normal_slaves = [s for s in slaves
                     if not self.is_testing_slave(s.slave)]

    for br in remaining:
      normal_slaves.sort(key=lambda s:
          len(self.get_slave_builders(s.slave, br)) +
          int(builder_config.IsGCESlave(s.slave.slavename)))

      # Iterate through slaves and choose the appropriate one.
      chromeos_config_name = br.properties.getProperty('chromeos_config', None)
      chromeos_config = configs.get(chromeos_config_name)
      builder = br.master.status.getBuilder(br.buildername)
      slaves = self.FilterSlaves(chromeos_config, builder.getSlaves())
      for s in normal_slaves:
        for builder_slave in slaves:
          if s.slave.slavename == builder_slave.getName():
            return s, br
    return None, None
