# -*- coding: utf-8 -*-
# Licensed under a 3-clause BSD style license - see LICENSE.rst

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
from os.path import abspath, dirname, exists, join, isfile
import shutil

import six

from asv import config
from asv.commands.run import Run
from asv.commands.publish import Publish


def test_workflow(tmpdir):
    # Tests a typical complete run/publish workflow
    tmpdir = six.text_type(tmpdir)
    local = abspath(dirname(__file__))
    os.chdir(tmpdir)

    shutil.copyfile(join(local, 'asv-machine.json'),
                    join(tmpdir, 'asv-machine.json'))

    conf = config.Config.from_json({
        'env_dir': join(tmpdir, 'env'),
        'benchmark_dir': join(local, 'benchmark'),
        'results_dir': join(tmpdir, 'results_workflow'),
        'html_dir': join(tmpdir, 'html'),
        'repo': 'https://github.com/spacetelescope/asv.git',
        'project': 'asv',
        'matrix': {
            "six": [None],
            "psutil": ["1.2", "2.1"]
        }
    })

    Run.run(conf, range_spec="initial..master", steps=2,
            _machine_file=join(tmpdir, 'asv-machine.json'), quick=True)

    assert len(os.listdir(join(tmpdir, 'results_workflow', 'orangutan'))) == 5
    assert len(os.listdir(join(tmpdir, 'results_workflow'))) == 2

    Publish.run(conf)

    assert isfile(join(tmpdir, 'html', 'index.html'))
    assert isfile(join(tmpdir, 'html', 'index.json'))
    assert isfile(join(tmpdir, 'html', 'asv.js'))
    assert isfile(join(tmpdir, 'html', 'asv.css'))

    Run.run(conf, range_spec="EXISTING",
            _machine_file=join(tmpdir, 'asv-machine.json'), quick=True)

    # Remove the benchmarks.json file to make sure publish can
    # regenerate it

    os.remove(join(tmpdir, "results_workflow", "benchmarks.json"))

    Publish.run(conf)


if __name__ == '__main__':
    from asv import console
    console.log.enable()

    from asv import machine
    machine.Machine.hardcoded_machine_name = 'orangutan'

    test_workflow('/tmp')
