'''
test_xss.py

Copyright 2012 Andres Riancho

This file is part of w3af, w3af.sourceforge.net .

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


class TestXSS(PluginTest):

    XSS_PATH = 'http://moth/w3af/audit/xss/'
    XSS_302_URL = 'http://moth/w3af/audit/xss/302/'
    XSS_URL_SMOKE = 'http://moth/w3af/audit/xss/'
    
    WAVSEP_PATH = 'http://localhost:8080/wavsep/active/RXSS-Detection-Evaluation-GET/'

    _run_configs = {
        'cfg': {
            'target': None,
            'plugins': {
                'audit': (
                    PluginConfig(
                        'xss',
                         ('persistent_xss', True, PluginConfig.BOOL)),
                ),
                'crawl': (
                    PluginConfig(
                        'web_spider',
                        ('only_forward', True, PluginConfig.BOOL)),
                )
            },
        },

        'smoke': {
            'target': XSS_URL_SMOKE + 'simple_xss_no_js.php?text=1',
            'plugins': {
                'audit': (
                    PluginConfig(
                        'xss',
                         ('persistent_xss', True, PluginConfig.BOOL)),
                ),
            },
        }

    }

    def normalize_kb_data(self, xss_vulns):
        '''
        Take the XSS vulns as input and translate them into a list of tuples
        which contain:
            - Vulnerable URL
            - Vulnerable parameter
            - All parameters that were sent
        '''
        kb_data = [(str(m.get_url()), m.get_var(), tuple(sorted(m.get_dc().keys())))
                   for m in (xv.get_mutant() for xv in xss_vulns)]
        return kb_data

    def normalize_expected_data(self, target_url, expected):
        '''
        Take a list with the expected vulnerabilities to be found  as input
        and translate them into a list of tuples which contain:
            - Vulnerable URL
            - Vulnerable parameter
            - All parameters that were sent
        '''
        expected_data = [(target_url + e[0], e[1], tuple(sorted(e[2]))
                          ) for e in expected]
        return expected_data

    @attr('smoke')
    def test_find_one_xss(self):
        '''
        Simplest possible test to verify that we identify XSSs.
        '''
        cfg = self._run_configs['smoke']
        self._scan(cfg['target'], cfg['plugins'])

        xss_vulns = self.kb.get('xss', 'xss')
        kb_data = self.normalize_kb_data(xss_vulns)
        
        EXPECTED = [('simple_xss_no_js.php', 'text', ['text']), ]
        expected_data = self.normalize_expected_data(self.XSS_URL_SMOKE,
                                                     EXPECTED)
        
        self.assertEquals(
            set(expected_data),
            set(kb_data),
        )

    def test_found_xss(self):
        cfg = self._run_configs['cfg']
        self._scan(self.XSS_PATH, cfg['plugins'])
        
        xss_vulns = self.kb.get('xss', 'xss')
        kb_data = self.normalize_kb_data(xss_vulns)
        
        expected = [
            # Trivial
            ('simple_xss.php', 'text', ['text']),

            # Simple filters
            ('simple_xss_no_script_2.php', 'text', ['text']),
            ('simple_xss_no_script.php', 'text', ['text']),
            ('simple_xss_no_js.php', 'text', ['text']),
            ('simple_xss_no_quotes.php', 'text', ['text']),
            ('no_tag_xss.php', 'text', ['text']),
            
            # More complex filters
            ('xss_filter_5.php', u'text', (u'text',)),
            ('xss_filter_6.php', u'text', (u'text',)),
            ('xss_filter_2.php', u'text', (u'text',)),
            ('xss_filter_7.php', u'text', (u'text',)),
            ('xss_filter.php', u'text', (u'text',)),
            
            # Forms with POST
            ('data_receptor.php', 'firstname', ['user', 'firstname']),
            ('data_receptor2.php', 'empresa', ['empresa', 'firstname']),
            ('data_receptor3.php', 'user', ['user', 'pass']),
                        
            # Persistent XSS
            ('stored/writer.php', 'a', ['a']),
        ]
        expected_data = self.normalize_expected_data(self.XSS_PATH,
                                                     expected)

        self.assertEquals(
            set(expected_data),
            set(kb_data),
        )

    def test_found_xss_with_redirect(self):
        cfg = self._run_configs['cfg']
        self._scan(self.XSS_302_URL, cfg['plugins'])
        
        xss_vulns = self.kb.get('xss', 'xss')
        kb_data = self.normalize_kb_data(xss_vulns)
        
        expected = [
            ('302.php', 'x', ('x',)),
            ('302.php', 'a', ('a',)),
            ('printer.php', 'a', ('a', 'added',)),
            ('printer.php', 'added', ('a', 'added',)),
            ('printer.php', 'added', ('added',)),
            ('printer.php', 'x', ('x', 'added')),
            ('printer.php', 'added', ('x', 'added'))
        ]
        expected_data = self.normalize_expected_data(self.XSS_302_URL,
                                                     expected)
        
        self.assertEquals(
            set(expected_data),
            set(kb_data),
        )


    def test_found_wavsep_get_xss(self):
        cfg = self._run_configs['cfg']
        self._scan(self.WAVSEP_PATH, cfg['plugins'])
        
        xss_vulns = self.kb.get('xss', 'xss')
        kb_data = self.normalize_kb_data(xss_vulns)
        
        expected = [
            ('Case01-Tag2HtmlPageScope.jsp', 'userinput', ['userinput']),
            ('Case02-Tag2TagScope.jsp', 'userinput', ['userinput']),
            ('Case03-Tag2TagStructure.jsp', 'userinput', ['userinput']),
            ('Case04-Tag2HtmlComment.jsp', 'userinput', ['userinput']),
            ('Case05-Tag2Frameset.jsp', 'userinput', ['userinput']),
            ('Case06-Event2TagScope.jsp', 'userinput', ['userinput']),
            ('Case07-Event2DoubleQuotePropertyScope.jsp', 'userinput', ['userinput']),
            ('Case08-Event2SingleQuotePropertyScope.jsp', 'userinput', ['userinput']),
            ('Case09-SrcProperty2TagStructure.jsp', 'userinput', ['userinput']),
            ('Case10-Js2DoubleQuoteJsEventScope.jsp', 'userinput', ['userinput']),
            ('Case11-Js2SingleQuoteJsEventScope.jsp', 'userinput', ['userinput']),
            ('Case12-Js2JsEventScope.jsp', 'userinput', ['userinput']),
            ('Case13-Vbs2DoubleQuoteVbsEventScope.jsp', 'userinput', ['userinput']),
            ('Case14-Vbs2SingleQuoteVbsEventScope.jsp', 'userinput', ['userinput']),
            ('Case15-Vbs2VbsEventScope.jsp', 'userinput', ['userinput']),
            ('Case16-Js2ScriptSupportingProperty.jsp', 'userinput', ['userinput']),
            ('Case17-Js2PropertyJsScopeDoubleQuoteDelimiter.jsp', 'userinput', ['userinput']),
            ('Case18-Js2PropertyJsScopeSingleQuoteDelimiter.jsp', 'userinput', ['userinput']),
            ('Case19-Js2PropertyJsScope.jsp', 'userinput', ['userinput']),
            ('Case20-Vbs2PropertyVbsScopeDoubleQuoteDelimiter.jsp', 'userinput', ['userinput']),
            ('Case21-Vbs2PropertyVbsScope.jsp', 'userinput', ['userinput']),
            ('Case22-Js2ScriptTagDoubleQuoteDelimiter.jsp', 'userinput', ['userinput']),
            ('Case23-Js2ScriptTagSingleQuoteDelimiter.jsp', 'userinput', ['userinput']),
            ('Case24-Js2ScriptTag.jsp', 'userinput', ['userinput']),
            ('Case25-Vbs2ScriptTagDoubleQuoteDelimiter.jsp', 'userinput', ['userinput']),
            ('Case26-Vbs2ScriptTag.jsp', 'userinput', ['userinput']),
            ('Case27-Js2ScriptTagOLCommentScope.jsp', 'userinput', ['userinput']),
            ('Case28-Js2ScriptTagMLCommentScope.jsp', 'userinput', ['userinput']),
            ('Case29-Vbs2ScriptTagOLCommentScope.jsp', 'userinput', ['userinput']),
            ('Case30-Tag2HtmlPageScopeMultipleVulnerabilities.jsp', 'userinput', ['userinput', 'userinput2']),
            ('Case30-Tag2HtmlPageScopeMultipleVulnerabilities.jsp', 'userinput2', ['userinput', 'userinput2']),
            ('Case31-Tag2HtmlPageScopeDuringException.jsp', 'userinput', ['userinput']),
            ('Case32-Tag2HtmlPageScopeValidViewstateRequired.jsp', 'userinput', ['userinput', '__VIEWSTATE']),
        ]
        
        expected_data = self.normalize_expected_data(self.WAVSEP_PATH,
                                                     expected)
        
        self.assertEquals(
            set(expected_data),
            set(kb_data),
        )
        