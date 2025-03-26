# Copyright (c) 2018 SAP SE or an SAP affiliate company. All rights reserved. This file is licensed
# under the Apache Software License, v. 2 except as noted otherwise in the LICENSE file
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys

steps_dir = os.path.abspath(os.path.dirname(__file__))

import util

import mako.template

def step_template(name):
    step_file = util.existing_file(os.path.join(steps_dir, name + '.mako'))

    return mako.template.Template(filename=step_file)

def step_def(name):
    template = step_template(name)

    return template.get_def(name + '_step').render

