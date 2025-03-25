# Copyright (C) 2011 Linaro Limited
#
# Author: Paul Larson <paul.larson@linaro.org>
#
# This file is part of LAVA Dispatcher.
#
# LAVA Dispatcher is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# LAVA Dispatcher is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along
# with this program; if not, see <http://www.gnu.org/licenses>.

import tempfile

from lava_dispatcher.config import get_device_config
from lava_dispatcher.client.master import LavaMasterImageClient
from lava_dispatcher.client.qemu import LavaQEMUClient
from lava_dispatcher.test_data import LavaTestData


class LavaContext(object):
    def __init__(self, target, image_type, dispatcher_config, oob_file, job_data):
        self.config = dispatcher_config
        self.job_data = job_data
        device_config = get_device_config(
            target, dispatcher_config.config_dir)
        client_type = device_config.get('client_type')
        if client_type == 'master':
            self._client = LavaMasterImageClient(self, device_config)
        elif client_type == 'qemu':
            self._client = LavaQEMUClient(self, device_config)
        else:
            raise RuntimeError(
                "this version of lava-dispatcher only supports master & qemu "
                "clients, not %r" % device_config.get('client_type'))
        self.test_data = LavaTestData()
        self.oob_file = oob_file
        self._host_result_dir = None

    @property
    def client(self):
        return self._client

    @property
    def lava_server_ip(self):
        return self.config.get("LAVA_SERVER_IP")

    @property
    def lava_image_tmpdir(self):
        return self.config.get("LAVA_IMAGE_TMPDIR")

    @property
    def lava_image_url(self):
        return self.config.get("LAVA_IMAGE_URL")

    @property
    def host_result_dir(self):
        if self._host_result_dir is None:
            self._host_result_dir = tempfile.mkdtemp()
        return self._host_result_dir

    @property
    def lava_result_dir(self):
        return self.config.get("LAVA_RESULT_DIR")

    @property
    def lava_cachedir(self):
        return self.config.get("LAVA_CACHEDIR")
