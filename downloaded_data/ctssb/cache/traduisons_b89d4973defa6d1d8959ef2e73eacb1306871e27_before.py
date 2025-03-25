#! /usr/bin/env python

# Copyright 2011 John E Tyree <johntyree@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301, USA.

"""
    Traduisons!
    http://traduisons.googlecode.com

    Python bindings to Google Translate RESTful API
"""

import base64
import htmlentitydefs
# In python <= 2.5, standard 'json' is not included 
try:
    import json
except(ImportError):
    import simplejson as json
import os
import re
import string
import sys
import threading
import urllib
import urllib2
from distutils import version


msg_VERSION = version.StrictVersion('0.4.4')
msg_DOWNLOAD = 'http://code.google.com/p/traduisons/downloads/list'
msg_LICENSE = """Traduisons! %s
http://traduisons.googlecode.com

Copyright (C) 201 John E Tyree <johntyree@gmail.com>
License GPLv3+: GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>
This is free software: you are free to change and redistribute it.
There is NO WARRANTY, to the extent permitted by law.
""" % (msg_VERSION,)
msg_BUGS = "Bugs, suggestions at <http://code.google.com/p/traduisons/issues/list>"

msg_HELP = """Type the name or code for the desired language.
Format:  <Input Language> | <Target Language>
fi|French    Finnish to French:
auto|en      Auto detect to English:
|ar          Change target Language to Arabic:
es|          Change starting Language to Spanish:

Please visit <http://code.google.com/p/traduisons/wiki> for help."""

appPath = os.path.dirname(__file__)
start_text = ""
from_lang = "auto"
to_lang = "en"

def echo(f):
    '''Print out f.__name__ BEGIN and f.__name__ END before and after f is called.'''
    def newfunc(*args, **kwargs):
        print f.__name__, "BEGIN"
        f(*args, **kwargs)
        print f.__name__, "END"
    return newfunc

class translator:
    '''Abstraction of the Google Translate RESTful API'''
    dictLang = {'Detect Language': 'auto',
                'Afrikaans': 'af',
                'Albanian': 'sq',
                'Arabic': 'ar',
                'Basque': 'eu',
                'Belarusian': 'be',
                'Bulgarian': 'bg',
                'Catalan': 'ca',
                'Chinese': 'zh-CN',
                'Chinese Simplified': 'zh-CN',
                'Chinese Traditional': 'zh-TW',
                'Croatian': 'hr',
                'Czech': 'cs',
                'Danish': 'da',
                'Dutch': 'nl',
                'English': 'en',
                'Estonian': 'et',
                'Filipino': 'tl',
                'Finnish': 'fi',
                'French': 'fr',
                'Gaelic': 'ga',
                'Galician': 'gl',
                'German': 'de',
                'Greek': 'el',
                'Haitian Creole': 'ht',
                'Hebrew': 'iw',
                'Hindi': 'hi',
                'Hungarian': 'hu',
                'Icelandic': 'is',
                'Indonesian': 'id',
                'Irish': 'ga',
                'Italian': 'it',
                'Japanese': 'ja',
                'Korean': 'ko',
                'Latvian': 'lv',
                'Lithuanian': 'lt',
                'Macedonian': 'mk',
                'Malay': 'ms',
                'Maltese': 'mt',
                'Norwegian': 'no',
                'Persian': 'fa',
                'Polish': 'pl',
                'Portuguese': 'pt',
                'Romanian': 'ro',
                'Russian': 'ru',
                'Serbian': 'sr',
                'Slovak': 'sk',
                'Slovenian': 'sl',
                'Spanish': 'es',
                'Swahili': 'sw',
                'Swedish': 'sv',
                'Thai': 'th',
                'Turkish': 'tr',
                'Ukrainian': 'uk',
                'Vietnamese': 'vi',
                'Welsh': 'cy',
                'Yiddish': 'yi',
                }
    headers = {'User-Agent': 'Traduisons/%s' % (msg_VERSION,)}

    class urlopener(urllib.URLopener):
        def __init__(self, *args, **kwargs):
            urllib.URLopener.__init__(self)
            self.addheader('User-Agent', "Traduisons/%s" % (msg_VERSION,))
        def urlread(self, url):
            try:
                txt = self.open(url).read().strip()
            except IOError, e:
                e.reason = e.strerror
                raise e
            return txt

    def __init__(self, from_lang = 'auto', to_lang = 'en', start_text = ''):
        if not self.from_lang(from_lang): self.from_lang('auto')
        if not self.to_lang(to_lang): self.to_lang('en')
        self._text = start_text
        self.urlread = self.urlopener().urlread

    def is_latest(self):
        '''Phone home to check if we are up to date.'''
        try:
            self.msg_LATEST
        except AttributeError:
            url = 'http://traduisons.googlecode.com/svn/trunk/LATEST-IS'
            try:
                ver = urllib2.urlopen(url).read().strip()
            except urllib2.HTTPError:
                return True
            try:
                self.msg_LATEST = version.StrictVersion(ver)
            except ValueError:
                pass
        return msg_VERSION >= self.msg_LATEST

    def update_languages(self, echo = False):
        '''
        Naively try to determine if new languages are available by scraping
        http://translate.google.com.
        If echo is false, return True if (we think) we succeeded, else False.
        If echo is true, return list of changes, else False.
        '''
        headers = self.headers
        url = 'http://code.google.com/apis/language/translate/v2/using_rest.html'
        req = urllib2.Request(url, None, headers)
        resp = urllib2.urlopen(req).read()
        regex = r'^\s+<td>([^<]*)</td>\n\s+<td><code>([^<]*)</code></td>'
        name_code = re.findall(regex, resp, 8)
        changes = []
        if name_code != []:
            name_code = dict(name_code)
            # These aren't listed, but are expected by users
            name_code.update([('Detect Language', 'auto'),
                             ('Chinese', 'zh-CN'),
                             ('Gaelic', 'ga'),
                             ('Korean', 'ko')])
            # Determine changes
            all_langs = set(self.dictLang.keys() + name_code.keys())
            for k in all_langs:
                new = name_code.has_key(k)
                old = self.dictLang.has_key(k)
                if old and not new:
                    changes.append('%s (%s): Removed' % (k, self.dictLang[k]))
                if new and not old:
                    changes.append('%s (%s): Added' % (k, name_code[k]))
            # Repopulate dictLang with new data
            self.dictLang = name_code
        else:
            return False
        if echo:
            return changes
        else:
            return True

    def pretty_print_languages(self, right_justify = True):
        '''
        Return a string of pretty-printed, newline-delimited languages in
        the format Name : code. "Detect Language : auto" is presented first.
        '''
        d = dict(self.dictLang) # force deep copy
        d.pop('Detect Language')
        l = ['Detect Language: auto']
        width = 0
        if right_justify:
            width = max([len(x) for x in d.keys()])
        for item in sorted(d.keys()):
            line = ''.join(["%", str(width), 's: %s']) % \
                (item, d[item])
            l.append(line)
        return '\n'.join(l)

    def to_lang(self, l = None):
        '''Get or set target language'''
        if l is not None:
            if l == 'auto':
                return False
            ## Check character code
            if l in self.dictLang.values():
                self._to_lang = l
            else:
                ## Check language name
                self._to_lang = self.dictLang.get(string.capitalize(l),
                                                  self._to_lang)
        return self._to_lang

    def from_lang(self, l = None):
        '''Get or set source language.'''
        if l is not None:
            ## Check character code
            if l in self.dictLang.values():
                self._from_lang = l
            else:
                ## Check language name
                self._from_lang = self.dictLang.get(string.capitalize(l),
                                                    self._from_lang)
        return self._from_lang

    def swapLang(self):
        '''Reverse direction the direction of translation.'''
        f = self._from_lang
        t = self._to_lang
        if not self.to_lang(f) or not self.from_lang(t):
            self._to_lang = t
            self._from_lang = f
            return False
        return True

    def raw_text(self, t = None):
        '''
        Get or set translation text, ignoring embedded directives such
        as '/' and '.'.
        '''
        if t is not None:
            t = unicode(t)
            self._text = t
        return self._text

    def text(self, text = None):
        '''
        Get or set translation text, handling embedded directives such
        as '/' and '.'.
        If a string is given, return a tuple containing the text to be
        translated and a stringified code indicating what operations were
        encoded. Available code are:
            SWAP - Traslation direction is reversed.
            EXIT - Program should terminate.
            HELP - Display help information.
            CHANGE - New translation languages have been selected.
            VERSION - Display version information.
            (False) - Boolean indicating no directives found.

        For example (in order):
            text('/test')  -> ('test', 'SWAP')
            text('-v')     -> ('test', 'VERSION')
            text('--help') -> ('test', 'HELP')
            text('pants')  -> ('pants', False)
        '''
        if text is None:
            return self._text
        if text == '':
            self._text = u''
            return
        RETURN_CODE = False
        if text in ('.exit', '.quit', '.quitter', 'exit()'):
            RETURN_CODE = 'EXIT'
        ## Use the '/' character to reverse translation direction.
        elif text[0] == '/' or text[-1] == '/':
            self.swapLang()
            try:
                # Cut off the '/' character if necessary
                if text[-1] == '/': text = text[:-1]
                elif text[0] == '/': text = text[1:]
            except:
                pass
            self._text = text
            RETURN_CODE = 'SWAP'
        elif text in ('?', 'help', '-h', '-help', '--help'):
            RETURN_CODE = 'HELP'
        ## Use '|' character to change translation language(s).
        elif text.find('|') + 1:
            self.from_lang(text[0:text.find('|')])
            self.to_lang(text[text.find('|') + 1:])
            RETURN_CODE = 'CHANGE'
        elif text in ('-v', '--version'):
                RETURN_CODE = 'VERSION'
        else:
            self._text = text
        return (self._text, RETURN_CODE)

    def detect_lang(self):
        '''
        Return a tuple containing a two letter string, a boolean
        "isReliable", and a confidence float corresponding to translation
        text.
        '''
        urldata = urllib.urlencode({'v': 1.0, 'q': self._text})
        url = 'http://ajax.googleapis.com/ajax/services/language/detect?%s' % \
                (urldata,)
        headers = self.headers
        req = urllib2.Request(url, None, headers)
        response = urllib2.urlopen(req).read()
        result = json.loads(response)
        if result['responseStatus'] != 200:
            self._error = ('Unable to detect language',
                           Exception(result['responseDetails']))
            result['responseData'] = {'language': '',
                                      'isReliable': False,
                                      'confidence': 0}
        return (result['responseData']['language'],
                result['responseData']['isReliable'],
                result['responseData']['confidence'])

    def translate(self):
        '''Return true if able to set self.result to translated text else,
        False.'''
        self.result = ''
        if self._text == '':
            return True
        try:
            # 'auto' needs to be set to blank now
            if self._from_lang == 'auto':
                from_lang_temp = ''
            else:
                from_lang_temp = self._from_lang
            langpair = '%s|%s' % (from_lang_temp, self._to_lang)
            urldata = urllib.urlencode({'v': 1.0,
                                        'q': self._text,
                                        'langpair': langpair,
                                       })
            url = 'http://ajax.googleapis.com/ajax/services/language/translate?%s' % \
                (urldata,)
            response = self.urlread(url)
            result = json.loads(response)
            if result['responseStatus'] != 200:
                self._error = ('Unable to translate',
                               Exception(result['responseDetails']))
                translation = ''
                return False
            translation = result['responseData']['translatedText']
            translation = self._unquotehtml(translation)
            if translation.lower() == self._text.lower():
                detected_lang = self.detect_lang()
                # Prefer Dutch over Afrikaans
                if detected_lang[0] == 'af' and detected_lang[1] == False:
                    detected_lang[0] = 'nl'
                    detected_lang[1] = False
                    detected_lang[2] = 0
                if detected_lang[0] == self.to_lang():
                    if self.from_lang() != 'auto':
                        self.swapLang()
                        print "Reversing translation direction..."
                        self.translate()
                        translation = self.result
        # If 'result' is empty (pretty generic error) handle exception.
        except TypeError, e:
            self._error = ('No translation available', e)
            return False
        # If the url ever changes...
        except IOError, e:
            self._error = (e.reason, e)
            return False
        finally:
            try:
                self.result = translation
            except NameError:
                pass
        return True

    def _unquotehtml(self, s):
        '''Convert a HTML quoted string into unicode object.
        Works with &#XX; and with &nbsp; &gt; etc.'''
        def convertentity(m):
            if m.group(1)=='#':
                try:
                    return chr(int(m.group(2)))
                except XValueError:
                    return '&#%s;' % (m.group(2),)
            try:
                return htmlentitydefs.entitydefs[m.group(2)]
            except KeyError:
                return ('&%s;' % (m.group(2),)).decode('ISO-8859-1'),
        return re.sub(r'&(#)?([^;]+);',convertentity,s)

## ------*------ End TRANSLATOR ------*------

def main():
    for arg in sys.argv[1:]:
        if arg in ('--help', '-h', "/?"):
            print msg_USAGE, "\n", msg_HELP
            sys.exit()
        elif arg in ('--no-gui', '-n', "/n"):
            guiflag = False
        elif arg in ("--version", "-v", "/v"):
            print msg_LICENSE
            sys.exit()
        else:
            print msg_USAGE, "\n", msg_BUGS
            sys.exit()

    ## Start traduisons!
    print "\nTraduisons! - %s\npowered by Google ..." % (msg_VERSION,)
    t = translator()
    if not t.is_latest():
        print "Version %s now available! %s" % (t.msg_LATEST,
                                                msg_DOWNLOAD)
    while True:
        t.text('')
        while t.text() == '':
            stringLang = t.from_lang() + "|" + t.to_lang() + ": "
            try:
                result = t.text(raw_input(stringLang))
                if result is False:
                   break
                elif result[1] == 'HELP':
                    print msg_HELP
                    print t.pretty_print_languages()
            except EOFError:
                print
                sys.exit()
        if t.translate():
            if t.result != '':
                if t.from_lang() == 'auto':
                    l = t.detect_lang()[0]
                    for k, v in t.dictLang.items():
                        if v == l:
                            print k, '-', v
                print t.result
        else:
            raise t.result[1]

if __name__ == '__main__': main()
