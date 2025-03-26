# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from master import master_config
from master.factory import annotator_factory

from buildbot.schedulers.basic import SingleBranchScheduler as Scheduler

factory_obj = annotator_factory.AnnotatorFactory()

def Builder(active_master, dname, sname, flavor, board):
  cbb_name = '%s-tot-chrome-pfq-informational' % (board,)
  builder = {
      'name': '%s (%s)' % (dname, flavor),
      'builddir': '%s-tot-chromeos-%s' % (flavor, sname),
      'category': '2chromium',
      'factory': factory_obj.BaseFactory('cros/cbuildbot'),
      'gatekeeper': 'pfq',
      'scheduler': 'chromium_cros',
      'notify_on_missing': True,
      'properties': {
          'cbb_config': cbb_name,
      },
  }
  if active_master.is_production_host:
    builder['properties']['cbb_debug'] = True
  return builder


def Update(_config, active_master, c):
  builders = [
      Builder(active_master, 'X86', 'x86', 'chromium', 'x86-generic'),
      Builder(active_master, 'AMD64', 'amd64', 'chromium', 'amd64-generic'),
      Builder(active_master, 'Daisy', 'daisy', 'chromium', 'daisy'),
  ]

  c['schedulers'] += [
      Scheduler(name='chromium_cros',
                branch='master',
                treeStableTimer=60,
                builderNames=[b['name'] for b in builders],
      ),
  ]
  c['builders'] += builders
