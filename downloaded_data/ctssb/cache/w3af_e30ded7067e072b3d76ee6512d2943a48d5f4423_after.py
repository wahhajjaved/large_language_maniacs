'''
test_error_pages.py

Copyright 2012 Andres Riancho

This file is part of w3af, http://w3af.org/ .

w3af is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation version 2 of the License.

w3af is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with w3af; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
'''
from nose.plugins.attrib import attr

from plugins.tests.helper import PluginTest, PluginConfig
import core.data.constants.severity as severity


@attr('smoke')
class TestErrorPages(PluginTest):

    target_url = 'http://moth/w3af/grep/error_pages/error_page.html'

    _run_configs = {
        'cfg': {
            'target': target_url,
            'plugins': {
                'grep': (PluginConfig('error_pages'),)
            }
        }
    }

    def test_found_vuln(self):
        cfg = self._run_configs['cfg']
        self._scan(cfg['target'], cfg['plugins'])

        infos = self.kb.get('error_pages', 'error_page')
        info = infos[0]

        self.assertEquals(1, len(infos), infos)
        self.assertEquals(self.target_url, str(info.get_url()))
        self.assertEquals(severity.INFORMATION, info.get_severity())
        self.assertTrue(info.get_name().startswith('Descriptive error page'))

        '''
        infos = self.kb.get('error_pages', 'server')
        info = infos[0]

        self.assertEquals(1, len(infos))
        self.assertEquals(self.target_url, str(info.get_url()))
        self.assertEquals(severity.INFORMATION, info.get_severity())
        self.assertTrue(info.get_name().startswith('Error page with information disclosure'))
        '''
