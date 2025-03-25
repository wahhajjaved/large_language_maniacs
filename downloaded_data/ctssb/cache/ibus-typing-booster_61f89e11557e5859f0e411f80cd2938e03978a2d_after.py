# -*- coding: utf-8 -*-
# vim:et sts=4 sw=4
#
# ibus-typing-booster - A completion input method for IBus
#
# Copyright (c) 2015-2016 Mike FABIAN <mfabian@redhat.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>

'''A module used by ibus-typing-booster to match emoji and similar
Unicode characters.

'''

import os
import sys
import re
import gzip
import json
import unicodedata
import html
from distutils.version import LooseVersion
from difflib import SequenceMatcher
import gettext
import itb_util

DOMAINNAME = 'ibus-typing-booster'
_ = lambda a: gettext.dgettext(DOMAINNAME, a)
N_ = lambda a: a

IMPORT_ENCHANT_SUCCESSFUL = False
try:
    import enchant
    IMPORT_ENCHANT_SUCCESSFUL = True
except (ImportError,):
    IMPORT_ENCHANT_SUCCESSFUL = False

IMPORT_PYKAKASI_SUCCESSFUL = False
try:
    from pykakasi import kakasi
    IMPORT_PYKAKASI_SUCCESSFUL = True
    KAKASI_INSTANCE = kakasi()
    KAKASI_INSTANCE.setMode('H', 'a') # default: Hiragana no conversion
    KAKASI_INSTANCE.setMode('K', 'a') # default: Katakana no conversion
    KAKASI_INSTANCE.setMode('J', 'a') # default: Japanese no conversion
    KAKASI_INSTANCE.setMode('r', 'Hepburn') # default: use Hepburn Roman table
    KAKASI_INSTANCE.setMode('C', True) # add space default: no Separator
    KAKASI_INSTANCE.setMode('c', False) # capitalize default: no Capitalize
except (ImportError,):
    IMPORT_PYKAKASI_SUCCESSFUL = False
    KAKASI_INSTANCE = None

IMPORT_PINYIN_SUCCESSFUL = False
try:
    import pinyin
    IMPORT_PINYIN_SUCCESSFUL = True
except (ImportError,):
    IMPORT_PINYIN_SUCCESSFUL = False

DATADIR = os.path.join(os.path.dirname(__file__), '../data')
# USER_DATADIR will be “~/.local/share/ibus-typing-booster/data” by default
USER_DATADIR = itb_util.xdg_save_data_path('ibus-typing-booster/data')

UNICODE_CATEGORIES = {
    'Cc': {'valid': False, 'major': 'Other', 'minor': 'Control'},
    # 'Cf' contains RIGHT-TO-LEFT MARK ...
    'Cf': {'valid': True, 'major': 'Other', 'minor': 'Format'},
    'Cn': {'valid': False, 'major': 'Other', 'minor': 'Not assigned'},
    'Co': {'valid': False, 'major': 'Other', 'minor': 'Private use'},
    'Cs': {'valid': False, 'major': 'Other', 'minor': 'Surrogate'},
    'Ll': {'valid': False, 'major': 'Letter', 'minor': 'Lowercase'},
    'Lm': {'valid': False, 'major': 'Letter', 'minor': 'Modifier'},
    'Lo': {'valid': False, 'major': 'Letter', 'minor': 'Other'},
    'Lt': {'valid': False, 'major': 'Letter', 'minor': 'Titlecase'},
    'Lu': {'valid': False, 'major': 'Letter', 'minor': 'Uppercase'},
    'Mc': {'valid': False, 'major': 'Mark', 'minor': 'Spacing combining'},
    'Me': {'valid': False, 'major': 'Mark', 'minor': 'Enclosing'},
    'Mn': {'valid': False, 'major': 'Mark', 'minor': 'Nonspacing'},
    'Nd': {'valid': False, 'major': 'Number', 'minor': 'Decimal digit'},
    'Nl': {'valid': False, 'major': 'Number', 'minor': 'Letter'},
    # 'No' contains SUPERSCRIPT ONE ...
    'No': {'valid': True, 'major': 'Number', 'minor': 'Other'},
    'Pc': {'valid': True, 'major': 'Punctuation', 'minor': 'Connector'},
    'Pd': {'valid': True, 'major': 'Punctuation', 'minor': 'Dash'},
    'Pe': {'valid': True, 'major': 'Punctuation', 'minor': 'Close'},
    'Pf': {'valid': True, 'major': 'Punctuation', 'minor': 'Final quote'},
    'Pi': {'valid': True, 'major': 'Punctuation', 'minor': 'Initial quote'},
    'Po': {'valid': True, 'major': 'Punctuation', 'minor': 'Other'},
    'Ps': {'valid': True, 'major': 'Punctuation', 'minor': 'Open'},
    'Sc': {'valid': True, 'major': 'Symbol', 'minor': 'Currency'},
    'Sk': {'valid': True, 'major': 'Symbol', 'minor': 'Modifier'},
    'Sm': {'valid': True, 'major': 'Symbol', 'minor': 'Math'},
    'So': {'valid': True, 'major': 'Symbol', 'minor': 'Other'},
    'Zl': {'valid': True, 'major': 'Separator', 'minor': 'Line'},
    'Zp': {'valid': True, 'major': 'Separator', 'minor': 'Paragraph'},
    'Zs': {'valid': True, 'major': 'Separator', 'minor': 'Space'},
}

# VALID_RANGES are taken from ibus-uniemoji
# (but not used anymore at the moment)
VALID_RANGES = (
    (0x0024, 0x0024), # DOLLAR SIGN
    (0x00a2, 0x00a5), # CENT SIGN, POUND SIGN, CURRENCY SIGN, YEN SIGN
    (0x058f, 0x058f), # ARMENIAN DRAM SIGN
    (0x060b, 0x060b), # AFGHANI SIGN
    (0x09f2, 0x09f3), # BENGALI RUPEE MARK, BENGALI RUPEE SIGN
    (0x09fb, 0x09fb), # BENGALI GANDA MARK
    (0x0af1, 0x0af1), # GUJARATI RUPEE SIGN
    (0x0bf9, 0x0bf9), # TAMIL RUPEE SIGN
    (0x0e3f, 0x0e3f), # THAI CURRENCY SYMBOL BAHT
    (0x17db, 0x17db), # KHMER CURRENCY SYMBOL RIEL
    (0x2000, 0x206f), # General Punctuation, Layout Controls,
                      # Invisible Operators
    (0x2070, 0x209f), # Superscripts and Subscripts
    (0x20a0, 0x20cf), # Currency Symbols
    (0x20d0, 0x20ff), # Combining Diacritical Marks for Symbols
    (0x2100, 0x214f), # Additional Squared Symbols, Letterlike Symbols
    (0x2150, 0x218f), # Number Forms
    (0x2190, 0x21ff), # Arrows
    (0x2200, 0x22ff), # Mathematical Operators
    (0x2300, 0x23ff), # Miscellaneous Technical, Floors and Ceilings
    (0x2336, 0x237a), # APL symbols
    (0x2400, 0x243f), # Control Pictures
    (0x2440, 0x245f), # Optical Character Recognition (OCR)
    (0x2460, 0x24ff), # Enclosed Alphanumerics
    (0x2500, 0x257f), # Box Drawing
    (0x2580, 0x259f), # Block Elements
    (0x25a0, 0x25ff), # Geometric Shapes
    (0x2600, 0x26ff), # Miscellaneous Symbols
    (0x2616, 0x2617), # Japanese Chess
    (0x2654, 0x265f), # Chess
    (0x2660, 0x2667), # Card suits
    (0x2630, 0x2637), # Yijing Trigrams
    (0x268a, 0x268f), # Yijing Monograms and Digrams
    (0x26c0, 0x26c3), # Checkers/Draughts
    (0x2700, 0x27bf), # Dingbats
    (0x27c0, 0x27ef), # Miscellaneous Mathematical Symbols-A
    (0x27f0, 0x27ff), # Supplemental Arrows-A
    (0x2800, 0x28ff), # Braille Patterns
    (0x2900, 0x297f), # Supplemental Arrows-B
    (0x2980, 0x29ff), # Miscellaneous Mathematical Symbols-B
    (0x2a00, 0x2aff), # Supplemental Mathematical Operators
    (0x2b00, 0x2bff), # Additional Shapes, Miscellaneous Symbols and Arrows
    (0xa838, 0xa838), # NORTH INDIC RUPEE MARK
    (0xfdfc, 0xfdfc), # RIAL SIGN
    (0xfe69, 0xfe69), # SMALL DOLLAR SIGN
    (0xff01, 0xff60), # Fullwidth symbols and currency signs
    (0x1f300, 0x1f5ff), # Miscellaneous Symbols and Pictographs
    (0x1f600, 0x1f64f), # Emoticons
    (0x1f650, 0x1f67f), # Ornamental Dingbats
    (0x1f680, 0x1f6ff), # Transport and Map Symbols
    (0x1f900, 0x1f9ff), # Supplemental Symbols and Pictographs
)

VALID_CHARACTERS = {
    'ﷺ', # ARABIC LIGATURE SALLALLAHOU ALAYHE WASALLAM
    'ﷻ', # ARABIC LIGATURE JALLAJALALOUHOU
    '﷽', # ARABIC LIGATURE BISMILLAH AR-RAHMAN AR-RAHEEM
}

SKIN_TONE_MODIFIERS = ('🏻', '🏼', '🏽', '🏾', '🏿')

def is_invisible(text):
    '''Checks whether a text is invisible

    Returns True if the text is invisible, False if not.

    May return True for some texts which are not completely
    invisible but hard to see in most fonts.

    :param character: The text
    :type character: String
    :rtype: Boolean

    Examples:

    >>> is_invisible('a')
    False

    >>> is_invisible(' ')
    True

    >>> is_invisible(' a')
    False

    >>> is_invisible('  ')
    True

    >>> is_invisible('')
    True
    '''
    invisible = True
    for character in text:
        if (unicodedata.category(character)
                not in ('Cc', 'Cf', 'Zl', 'Zp', 'Zs')):
            invisible = False
    return invisible

def _in_range(codepoint):
    '''Checks whether the codepoint is in one of the valid ranges

    Returns True if the codepoint is in one of the valid ranges,
    else it returns False.

    :param codepoint: The Unicode codepoint to check
    :type codepoint: Integer
    :rtype: Boolean

    Examples:

    >>> _in_range(0x1F915)
    True

    >>> _in_range(0x1F815)
    False

    >>> _in_range(ord('€'))
    True

    >>> _in_range(ord('₹'))
    True

    >>> _in_range(ord('₺'))
    True
    '''
    return any([x <= codepoint <= y for x, y in VALID_RANGES])

SPANISH_419_LOCALES = (
    'es_AR', 'es_MX', 'es_BO', 'es_CL', 'es_CO', 'es_CR',
    'es_CU', 'es_DO', 'es_EC', 'es_GT', 'es_HN', 'es_NI',
    'es_PA', 'es_PE', 'es_PR', 'es_PY', 'es_SV', 'es_US',
    'es_UY', 'es_VE',)

def expand_languages(languages):
    '''Expands the given list of languages by including fallbacks.

    Returns a possibly longer list of languages by adding
    aliases and fallbacks.

    :param languages: A list of languages (or locale names)
    :type languages: List of strings
    :rtype: List  of strings

    Examples:

    >>> expand_languages(['es_MX', 'es_ES', 'ja_JP'])
    ['es_MX', 'es_419', 'es', 'es_ES', 'es', 'ja_JP', 'ja', 'en']

    >>> expand_languages(['zh_Hant', 'zh_CN', 'zh_TW', 'zh_SG', 'zh_HK', 'zh_MO'])
    ['zh_Hant', 'zh_CN', 'zh', 'zh_TW', 'zh_Hant', 'zh_SG', 'zh', 'zh_HK', 'zh_Hant', 'zh_MO', 'zh_Hant', 'en']
    '''
    expanded_languages = []
    for language in languages:
        expanded_languages.append(language)
        if language in SPANISH_419_LOCALES:
            expanded_languages.append('es_419')
        if language in ('zh_TW', 'zh_HK', 'zh_MO'):
            expanded_languages.append('zh_Hant')
        if language[:2] == 'en':
            expanded_languages.append('en_001')
        if (language not in ('zh_TW', 'zh_HK', 'zh_MO', 'zh_Hant')
                and language.split('_')[:1] != [language]):
            expanded_languages += language.split('_')[:1]
    if 'en' not in expanded_languages:
        expanded_languages.append('en')
    return expanded_languages

def _find_path_and_open_function(dirnames, basenames, subdir=''):
    '''Find the first existing file of a list of basenames and dirnames

    For each file in “basenames”, tries whether that file or the
    file with “.gz” added can be found in the list of directories
    “dirnames” where “subdir” is added to each directory in the list.

    Returns a tuple (path, open_function) where “path” is the
    complete path of the first file found and the open function
    is either “open()” or “gzip.open()”.

    :param dirnames: A list of directories to search in
    :type dirnames: List of strings
    :param basenames: A list of file names to search for
    :type basenames: List of strings
    :rtype: A tuple (path, open_function)
    :param subdir: A subdirectory to be added to each directory in the list
    :type subdir: String

    '''
    for basename in basenames:
        for dirname in dirnames:
            path = os.path.join(dirname, subdir, basename)
            if os.path.exists(path):
                if path.endswith('.gz'):
                    return (path, gzip.open)
                else:
                    return (path, open)
            path = os.path.join(dirname, basename + '.gz')
            if os.path.exists(path):
                return (path, gzip.open)
    return ('', None)

class EmojiMatcher():
    '''A class to find Emoji which best match a query string'''

    def __init__(self, languages=('en_US',),
                 unicode_data=True, unicode_data_all=False,
                 emoji_unicode_min='1.0',
                 emoji_unicode_max='100.0',
                 cldr_data=True, quick=True,
                 non_fully_qualified=False,
                 romaji=True):
        '''
        Initialize the emoji matcher

        :param languages: A list of languages to use for matching emoji
        :type languages: List or tuple of strings
        :param unicode_data: Whether to load the UnicodeData.txt file as well
        :type unicode_data: Boolean
        :param unicode_data_all: Whether to load *all* of the Unicode characters
                                  from UnicodeData.txt. If False, most regular
                                  letters are omitted.
        :type unicode_data_all: Boolean
        :param cldr_data: Whether to load data from CLDR as well
        :type cldr_data: Boolean
        :param quick: Whether to do a quicker but slighly less precise match.
                      Quick matching is about 4 times faster and usually
                      good enough.
        :type quick: Boolean
        :param romaji: Whether to add Latin transliteration for Japanese.
                       Works only when pykakasi is available, if this is not
                       the case, this option is ignored.
        :type romaji: Boolean
        '''
        self._languages = languages
        self._gettext_translations = {}
        for language in expand_languages(self._languages):
            mo_file = gettext.find(DOMAINNAME, languages=[language])
            if (mo_file
                    and
                    '/' + language  + '/LC_MESSAGES/' + DOMAINNAME + '.mo'
                    in mo_file):
                # Get the gettext translation instance only if a
                # translation file for this *exact* language was
                # found.  Ignore it if only a fallback was found. For
                # example, if “de_DE” was requested and only “de” was
                # found, ignore it.
                try:
                    self._gettext_translations[language] = gettext.translation(
                        DOMAINNAME, languages=[language])
                except (OSError, ):
                    self._gettext_translations[language] = None
            else:
                self._gettext_translations[language] = None
        self._unicode_data_all = unicode_data_all
        self._emoji_unicode_min = emoji_unicode_min
        self._emoji_unicode_max = emoji_unicode_max
        self._quick = quick
        self._non_fully_qualified = non_fully_qualified
        self._romaji = romaji
        self._enchant_dicts = []
        if IMPORT_ENCHANT_SUCCESSFUL:
            for language in self._languages:
                if enchant.dict_exists(language):
                    self._enchant_dicts.append(enchant.Dict(language))
        # From the documentation
        # (https://docs.python.org/3.6/library/difflib.html):
        # “SequenceMatcher computes and caches detailed information
        # about the second sequence, so if you want to compare one
        # sequence against many sequences, use set_seq2() to set the
        # commonly used sequence once and call set_seq1() repeatedly,
        # once for each of the other sequences.”
        self._matcher = SequenceMatcher(
            isjunk=None, a='', b='', autojunk=False)
        self._match_cache = {}
        self._string1 = ''
        self._seq1 = ''
        self._len1 = 0
        self._string2 = ''
        self._string2_number_of_words = 0
        self._string2_word_list = []
        self._seq2 = ''
        self._len2 = 0
        self._emoji_dict = {}
        self._candidate_cache = {}
        # The three data sources are loaded in this order on purpose.
        # The data from Unicode is loaded first to put the official
        # names first into the list of names to display the official
        # names in the candidates, if possible.  The second best names
        # are the long names of emojione.
        if unicode_data:
            self._load_unicode_data()
        self._load_unicode_emoji_data()
        self._load_unicode_emoji_sequences()
        self._load_unicode_emoji_zwj_sequences()
        self._load_unicode_emoji_test()
        self._load_emojione_data()
        if cldr_data:
            for language in expand_languages(self._languages):
                self._load_cldr_annotation_data(language, 'annotations')
                self._load_cldr_annotation_data(language, 'annotationsDerived')

    def get_languages(self):
        '''Returns a copy of the list of languages of this EmojiMatcher

        Useful to check whether an already available EmojiMatcher instance
        can be used or whether one needs a new instance because one needs
        a different list of languages.

        Note that the order of that list is important, a matcher which
        supports the same languages but in an different order might
        return different results.

        :rtype: A list of strings

        Examples:

        >>> m = EmojiMatcher(languages = ['en_US', 'it_IT', 'es_MX', 'es_ES', 'de_DE', 'ja_JP'])
        >>> m.get_languages()
        ['en_US', 'it_IT', 'es_MX', 'es_ES', 'de_DE', 'ja_JP']

        '''
        # Use list() to make a copy instead of self._languages[:] because
        # the latter might return the default tuple ('en_US',) instead
        # of a list ['en_US'] which makes comparison with another list
        # more inconvenient:
        return list(self._languages)

    def variation_selector_16_normalize(
            self, emoji_string, non_fully_qualified=False):
        '''Removes or adds emoji presentation selectors (U+FE0F VARIATION
        SELECTOR-16)

        Returns the possibly changed sequence.

        If emoji_string is equal to '\ufe0f', it is returned unchanged.

        See:

        http://unicode.org/reports/tr51/#def_fully_qualified_emoji_zwj_sequence
        http://unicode.org/reports/tr51/#def_non_fully_qualified_emoji_zwj_sequence

        :param emoji_string: The emoji sequence to change.
        :type emoji_string: String
        :param non_fully_qualified: If True, remove all VS16 characters
                                    If False, make it a fully qualified
                                    sequence using VS16 characters a needed.
        :type non_fully_qualified: Boolean
        :rtype: String

        Examples:

        >>> matcher = EmojiMatcher()

        If non_fully_qualified=True, all variation selectors
        are removed from a sequence, no matter whether the sequence
        was correct or not:

        >>> matcher.variation_selector_16_normalize('⛹\ufe0f\u200d♀\ufe0f', non_fully_qualified=True)
        '⛹\u200d♀'

        >>> matcher.variation_selector_16_normalize('⛹🏿\u200d♀\ufe0f', non_fully_qualified=True)
        '⛹🏿\u200d♀'

        >>> matcher.variation_selector_16_normalize('#\ufe0f⃣', non_fully_qualified=True)
        '#⃣'

        >>> matcher.variation_selector_16_normalize('#⃣\ufe0f', non_fully_qualified=True)
        '#⃣'

        If non_fully_qualified=False, variation selectors are added to
        sequences as needed and incorrect sequences are repaired:

        >>> matcher.variation_selector_16_normalize('⛹🏿\ufe0f\u200d♀\ufe0f', non_fully_qualified=False)
        '⛹🏿\u200d♀\ufe0f'

        >>> matcher.variation_selector_16_normalize('⛹\ufe0f🏿\u200d♀\ufe0f', non_fully_qualified=False)
        '⛹🏿\u200d♀\ufe0f'

        >>> matcher.variation_selector_16_normalize('⛹\u200d\ufe0f♀', non_fully_qualified=False)
        '⛹\ufe0f\u200d♀\ufe0f'

        >>> matcher.variation_selector_16_normalize('#⃣\ufe0f', non_fully_qualified=False)
        '#\ufe0f⃣'

        >>> matcher.variation_selector_16_normalize('⛹\ufe0f♀', non_fully_qualified=False)
        '⛹\ufe0f♀\ufe0f'

        >>> matcher.variation_selector_16_normalize('⛹', non_fully_qualified=False)
        '⛹\ufe0f'
        '''
        if emoji_string != '\ufe0f':
            emoji_string = emoji_string.replace('\ufe0f', '')
        if non_fully_qualified:
            return emoji_string
        else:
            retval = ''
            length = len(emoji_string)
            for index, character in enumerate(emoji_string):
                retval += character
                if ((character not in SKIN_TONE_MODIFIERS)
                    and ('Emoji' in self.properties(character))
                    and ('Emoji_Presentation'
                         not in self.properties(character))
                    and not (index < length - 1
                             and
                             emoji_string[index + 1]
                             in SKIN_TONE_MODIFIERS)):
                    retval += '\ufe0f'
            return retval

    def _add_to_emoji_dict(self, emoji_dict_key, values_key, values):
        '''Adds data to the emoji_dict if not already there'''
        if not emoji_dict_key or not values_key or not values:
            return
        emoji_dict_key = (
            self.variation_selector_16_normalize(
                emoji_dict_key[0], non_fully_qualified=True),
            emoji_dict_key[1])
        if emoji_dict_key not in self._emoji_dict:
            self._emoji_dict[emoji_dict_key] = {}
        if type(values) is list:
            if (values_key not in self._emoji_dict[emoji_dict_key]):
                self._emoji_dict[emoji_dict_key][values_key] = []
            for value in values:
                if (value not in
                        self._emoji_dict[emoji_dict_key][values_key]):
                    self._emoji_dict[emoji_dict_key][values_key] += [value]
        else:
            self._emoji_dict[emoji_dict_key][values_key] = values

    def _load_unicode_data(self):
        '''Loads emoji names from UnicodeData.txt'''
        dirnames = (USER_DATADIR, DATADIR,
                    # On Fedora, the “unicode-ucd” package has the
                    # UnicodeData.txt file here:
                    '/usr/share/unicode/ucd')
        basenames = ('UnicodeData.txt',)
        (path, open_function) = _find_path_and_open_function(
            dirnames, basenames)
        if not path:
            sys.stderr.write(
                '_load_unicode_data(): could not find "%s" in "%s"\n'
                %(basenames, dirnames))
            return
        with open_function(path, mode='rt') as unicode_data_file:
            for line in unicode_data_file.readlines():
                if not line.strip():
                    continue
                codepoint_string, name, category = line.split(';')[:3]
                codepoint_integer = int(codepoint_string, 16)
                emoji_string = chr(codepoint_integer)
                if category in ('Cc', 'Co', 'Cs'):
                    # Never load control characters (“Cc”), they cause
                    # too much problems when trying to display
                    # them. Never load the “First” and “Last”
                    # characters of private use characters “Co” and
                    # surrogates (“Cs”) either as these are completely
                    # useless.
                    continue
                if (not self._unicode_data_all
                        and not UNICODE_CATEGORIES[category]['valid']
                        and emoji_string not in VALID_CHARACTERS):
                    continue
                self._add_to_emoji_dict(
                    (emoji_string, 'en'), 'names', [name.lower()])
                self._add_to_emoji_dict(
                    (emoji_string, 'en'),
                    'ucategories', [
                        category,
                        UNICODE_CATEGORIES[category]['major'],
                        UNICODE_CATEGORIES[category]['minor'],
                    ]
                )

    def _load_unicode_emoji_data(self):
        '''
        Loads emoji property data from emoji-data.txt

        http://unicode.org/Public/emoji/5.0/emoji-data.txt
        '''
        dirnames = (USER_DATADIR, DATADIR)
        basenames = ('emoji-data.txt',)
        (path, open_function) = _find_path_and_open_function(
            dirnames, basenames)
        if not path:
            sys.stderr.write(
                '_load_unicode_emoji_data(): could not find "%s" in "%s"\n'
                %(basenames, dirnames))
            return
        with open_function(path, mode='rt') as unicode_emoji_data_file:
            for line in unicode_emoji_data_file.readlines():
                unicode_version = ''
                pattern = re.compile(
                    r'[^;]*;[^;]*#\s*(?P<uversion>[0-9]+\.[0-9]+)\s*'
                    + r'\[[0-9]+\]')
                match  = pattern.match(line)
                if match and match.group('uversion'):
                    unicode_version = match.group('uversion')
                line = re.sub(r'#.*$', '', line).strip()
                if not line:
                    continue
                codepoint_string, property = [
                    x.strip() for x in line.split(';')[:2]]
                codepoint_range = [
                    int(x, 16) for x in codepoint_string.split('..')]
                if len(codepoint_range) == 1:
                    codepoint_range.append(codepoint_range[0])
                assert len(codepoint_range) == 2
                for codepoint in range(
                        codepoint_range[0], codepoint_range[1] + 1):
                    emoji_string = chr(codepoint)
                    self._add_to_emoji_dict(
                        (emoji_string, 'en'), 'properties', [property])
                    if unicode_version:
                        self._add_to_emoji_dict(
                            (emoji_string, 'en'), 'uversion', unicode_version)

    def _load_unicode_emoji_sequences(self):
        '''
        Loads emoji property data from emoji-data.txt

        http://unicode.org/Public/emoji/5.0/emoji-sequences.txt
        '''
        dirnames = (USER_DATADIR, DATADIR)
        basenames = ('emoji-sequences.txt',)
        (path, open_function) = _find_path_and_open_function(
            dirnames, basenames)
        if not path:
            sys.stderr.write(
                '_load_unicode_emoji_sequences(): could not find "%s" in "%s"\n'
                %(basenames, dirnames))
            return
        with open_function(path, mode='rt') as unicode_emoji_sequences_file:
            for line in unicode_emoji_sequences_file.readlines():
                unicode_version = ''
                pattern = re.compile(
                    r'[^;]*;[^;]*;[^;]*#\s*(?P<uversion>[0-9]+\.[0-9]+)\s*'
                    + r'\[[0-9]+\]')
                match  = pattern.match(line)
                if match and match.group('uversion'):
                    unicode_version = match.group('uversion')
                line = re.sub(r'#.*$', '', line).strip()
                if not line:
                    continue
                codepoints, property, name = [
                    x.strip() for x in line.split(';')[:3]]
                if codepoints == '0023 FE0F 20E3' and name == 'keycap:':
                    name = 'keycap: #'
                emoji_string = ''
                for codepoint in codepoints.split(' '):
                    emoji_string += chr(int(codepoint, 16))
                if emoji_string:
                    self._add_to_emoji_dict(
                        (emoji_string, 'en'), 'properties', [property])
                    self._add_to_emoji_dict(
                        (emoji_string, 'en'), 'names', [name.lower()])
                    if unicode_version:
                        self._add_to_emoji_dict(
                            (emoji_string, 'en'), 'uversion', unicode_version)

    def _load_unicode_emoji_zwj_sequences(self):
        '''
        Loads emoji property data from emoji-zwj-sequences.txt

        http://unicode.org/Public/emoji/5.0/emoji-zwj-sequences.txt
        '''
        dirnames = (USER_DATADIR, DATADIR)
        basenames = ('emoji-zwj-sequences.txt',)
        (path, open_function) = _find_path_and_open_function(
            dirnames, basenames)
        if not path:
            sys.stderr.write(
                '_load_unicode_emoji_zwj_sequences(): could not find "%s" in "%s"\n'
                %(basenames, dirnames))
            return
        with open_function(path, mode='rt') as unicode_emoji_zwj_sequences_file:
            for line in unicode_emoji_zwj_sequences_file.readlines():
                unicode_version = ''
                pattern = re.compile(
                    r'[^;]*;[^;]*;[^;]*#\s*(?P<uversion>[0-9]+\.[0-9]+)\s*'
                    + r'\[[0-9]+\]')
                match  = pattern.match(line)
                if match and match.group('uversion'):
                    unicode_version = match.group('uversion')
                line = re.sub(r'#.*$', '', line).strip()
                if not line:
                    continue
                codepoints, property, name = [
                    x.strip() for x in line.split(';')[:3]]
                emoji_string = ''
                for codepoint in codepoints.split(' '):
                    emoji_string += chr(int(codepoint, 16))
                if emoji_string:
                    self._add_to_emoji_dict(
                        (emoji_string, 'en'), 'properties', [property])
                    self._add_to_emoji_dict(
                        (emoji_string, 'en'), 'names', [name.lower()])
                    if unicode_version:
                        self._add_to_emoji_dict(
                            (emoji_string, 'en'), 'uversion', unicode_version)

    def _load_unicode_emoji_test(self):
        '''Loads emoji property data from emoji-test.txt

        http://unicode.org/Public/emoji/4.0/emoji-test.txt

        This is mostly for emoji sorting and for some categorization

        Don’t use the 5.0 file until Emoji 5.0 is released and some
        fonts support it, using the 5.0 file now results in lots of
        ugly replacement characters when browsing the categories.

        For the other files emoji-data.txt, emoji-zwj-sequences.txt,
        and emoji-sequences.txt it is OK to use the draft 5.0 versions
        as they don’t cause proposed characters to show up when
        browsing the categories. The proposed characters only show up
        when searching and in that case it is OK I think, it is not so
        obviously ugly. And I think it is useful for the proposed
        characters to be searchable.

        '''
        dirnames = (USER_DATADIR, DATADIR)
        basenames = ('emoji-test.txt',)
        (path, open_function) = _find_path_and_open_function(
            dirnames, basenames)
        if not path:
            sys.stderr.write(
                '_load_unicode_emoji_test(): could not find "%s" in "%s"\n'
                %(basenames, dirnames))
            return
        with open_function(path, mode='rt') as unicode_emoji_test_file:
            group = ''
            subgroup = ''
            cldr_order = 0
            cldr_group_to_emojione_category = {
                'Smileys & People': N_('people'),
                'Animals & Nature': N_('nature'),
                'Food & Drink': N_('food'),
                'Travel & Places': N_('travel'),
                'Activities': N_('activity'),
                'Objects': N_('objects'),
                'Symbols': N_('symbols'),
                'Flags': N_('flags'),
                'Modifiers': N_('modifier'), # not  in emoji-test.txt
                'Regional': N_('regional'), # not  in emoji-test.txt
            }
            cldr_subgroup_to_emojione_category = {
                'person-sport':  N_('activity'),
            }
            for line in unicode_emoji_test_file.readlines():
                pattern = re.compile(r'# group:(?P<group>.+)$')
                match = pattern.match(line)
                if match and match.group('group'):
                    group = match.group('group').strip()
                    continue
                pattern = re.compile(r'# subgroup:(?P<subgroup>.+)$')
                match = pattern.match(line)
                if match and match.group('subgroup'):
                    subgroup = match.group('subgroup').strip()
                    continue
                line = re.sub(r'#.*$', '', line).strip()
                if not line:
                    continue
                codepoints, property = [
                    x.strip() for x in line.split(';')[:2]]
                if property == 'non-fully-qualified':
                    # The non-fully-qualified sequences are
                    # all duplicates of the fully-qualified
                    # sequences.
                    continue
                cldr_order += 1
                emoji_string = ''
                for codepoint in codepoints.split(' '):
                    emoji_string += chr(int(codepoint, 16))
                if emoji_string:
                    categories = [cldr_group_to_emojione_category[group]]
                    if subgroup in cldr_subgroup_to_emojione_category:
                        categories.append(
                            cldr_subgroup_to_emojione_category[subgroup])
                    self._add_to_emoji_dict(
                        (emoji_string, 'en'), 'cldr_order', str(cldr_order))
                    self._add_to_emoji_dict(
                        (emoji_string, 'en'), 'categories', categories)
                    self._add_translated_categories_to_emoji_dict(
                        emoji_string, categories)

    def _load_emojione_data(self):
        '''
        Loads emoji names, aliases, keywords, and categories from
        the emojione.json file.
        '''
        dirnames = (USER_DATADIR, DATADIR,
                    # On Fedora >= 25 there is a “nodejs-emojione-json“
                    # package which has the “emoji.json” file here:
                    '/usr/lib/node_modules/emojione/')
        basenames = ('emojione.json', 'emoji.json')
        (path, open_function) = _find_path_and_open_function(
            dirnames, basenames)
        if not path:
            sys.stderr.write(
                '_load_emojione_data(): could not find "%s" in "%s"\n'
                %(basenames, dirnames))
            return
        with open_function(path, mode='rt') as emoji_one_file:
            emojione = json.load(emoji_one_file)
        if '1f600' not in emojione:
            emojione_version = 2
        else:
            emojione_version = 3
        for dummy_emojione_key, emojione_value in emojione.items():
            if emojione_version >= 3:
                codepoints = emojione_value['code_points']['output']
            else:
                codepoints = emojione_value['unicode']
                # ZWJ emojis are in the 'unicode_alt' field:
                if ('unicode_alt' in emojione_value
                        and '200d' in emojione_value['unicode_alt']):
                    codepoints = emojione_value['unicode_alt']

            emoji_string = ''.join([
                chr(int(codepoint, 16)) for codepoint in codepoints.split('-')
            ])

            # emojione has names like “kiss (woman,woman)”, “couple
            # (man,man)” “family (man,man,girl,boy)”, “cocos (keeling)
            # islands”, “ceuta, melilla” …. The parentheses and commas
            # disturb the matching because my matching assumes that
            # words are seperated only by spaces. And they also match
            # too much for ASCII-smiley query strings like “:-)”. But
            # they are nicer for display. Therefore, if a name
            # contains such characters keep both the original name
            # (for display) and the name with these characters removed
            display_name = emojione_value['name'].lower()
            match_name = re.sub(r' ?[(,)] ?', r' ', display_name).strip(' ')
            names = [display_name]
            shortname = emojione_value[
                'shortname'].replace('_', ' ').strip(':')
            if emojione_version >= 3:
                aliases = [x.replace('_', ' ').strip(':')
                           for x in emojione_value['shortname_alternates']]
                ascii_aliases = emojione_value['ascii']
            else:
                aliases = [x.replace('_', ' ').strip(':')
                           for x in emojione_value['aliases']]
                ascii_aliases = emojione_value['aliases_ascii']
            if match_name not in names:
                names += [match_name]
            if shortname not in names:
                names += [shortname]
            for alias in aliases + ascii_aliases:
                if alias not in names:
                    names += [alias]

            categories = [emojione_value['category']]
            # EmojiOne has duplicate entries in the keywords.  The
            # keywords also have random order (maybe because of the
            # way json.load(file) works?), sort them to get
            # reproducible output in the test cases (if the order
            # changes, which keyword matches last may change, that
            # does not change the score but it may have an effect on
            # the additional information added to the display string
            # added because of a keyword match).
            keywords = sorted(list(set(emojione_value['keywords'])))
            if '' in keywords:
                # EmojiOne 3 has some empty strings in the keyword lists
                # remove them:
                keywords.remove('')

            if emojione_version >= 3:
                emoji_order = emojione_value['order']
            else:
                emoji_order = emojione_value['emoji_order']

            if emoji_string == '🏳🌈':
                # The rainbow flag should be a zwj sequence.
                # This is a bug in emojione version 2:
                # https://github.com/Ranks/emojione/issues/455
                # Fix it here:
                emoji_string = '🏳\u200d🌈'

            if (len(emoji_string) == 1
                    and emoji_string in '🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿'):
                # Work around bug in emojione version 3.0
                # https://github.com/Ranks/emojione/issues/476
                # The category should *not* be 'people':
                categories = ['regional']

            if emoji_string in SKIN_TONE_MODIFIERS:
                # Work around bug in emojione version 3.0
                # https://github.com/Ranks/emojione/issues/476
                # The category should *not* be 'people':
                categories = ['modifier']

            if (len(emoji_string) == 2 and emoji_string[1] == '\ufe0f'
                    and emoji_string[0] in '#*0123456789'):
                # Work around bug in emojione version 3.0
                # https://github.com/Ranks/emojione/issues/476
                # The category should *not* be 'people':
                categories = []

            self._add_to_emoji_dict(
                (emoji_string, 'en'), 'names', names)
            self._add_to_emoji_dict(
                (emoji_string, 'en'), 'categories', categories)
            self._add_to_emoji_dict(
                (emoji_string, 'en'), 'keywords', keywords)
            self._add_to_emoji_dict(
                (emoji_string, 'en'), 'emoji_order', emoji_order)

            self._add_translated_categories_to_emoji_dict(
                emoji_string, categories)

    def _add_translated_categories_to_emoji_dict(
            self, emoji_string, categories):
        '''
        Add translated versions of categories for an emoji
        to self._emoji_dict

        :param emoji_string: An emoji
        :type emoji_string: String
        :param categories: The categories of the emoji
        :type categories: List of strings
        '''
        dummy_categories_to_translate = [
            # Translators: This is a name for a category of emoji
            N_('activity'),
            # Translators: This is a name for a category of emoji
            N_('flags'),
            # Translators: This is a name for a category of emoji
            N_('food'),
            # Translators: This is a name for a category of emoji
            N_('modifier'),
            # Translators: This is a name for a category of emoji
            N_('nature'),
            # Translators: This is a name for a category of emoji
            N_('objects'),
            # Translators: This is a name for a category of emoji
            N_('people'),
            # Translators: This is a name for a category of emoji
            N_('regional'),
            # Translators: This is a name for a category of emoji
            N_('symbols'),
            # Translators: This is a name for a category of emoji
            N_('travel'),
        ]

        if (IMPORT_PYKAKASI_SUCCESSFUL
                and 'ja' in expand_languages(self._languages)):
            KAKASI_INSTANCE.setMode('H', 'H')
            KAKASI_INSTANCE.setMode('K', 'H')
            KAKASI_INSTANCE.setMode('J', 'H')
            kakasi_converter = KAKASI_INSTANCE.getConverter()

        for language in expand_languages(self._languages):
            if self._gettext_translations[language]:
                translated_categories = []
                for category in categories:
                    translated_category = self._gettext_translations[
                        language].gettext(category)
                    translated_categories.append(
                        translated_category)
                    if language == 'ja' and IMPORT_PYKAKASI_SUCCESSFUL:
                        translated_category_hiragana = (
                            kakasi_converter.do(
                                translated_category))
                        if (translated_category_hiragana
                                != translated_category):
                            translated_categories.append(
                                translated_category_hiragana)
                        if self._romaji:
                            KAKASI_INSTANCE.setMode('H', 'a')
                            KAKASI_INSTANCE.setMode('K', 'a')
                            KAKASI_INSTANCE.setMode('J', 'a')
                            # default: use Hepburn Roman table
                            KAKASI_INSTANCE.setMode('r', 'Hepburn')
                            # add space default: no Separator
                            KAKASI_INSTANCE.setMode('C', True)
                            # capitalize default: no Capitalize
                            KAKASI_INSTANCE.setMode('c', False)
                            kakasi_converter = KAKASI_INSTANCE.getConverter()
                            translated_category_romaji = (
                                kakasi_converter.do(
                                    translated_category)).lower()
                            KAKASI_INSTANCE.setMode('H', 'H')
                            KAKASI_INSTANCE.setMode('K', 'H')
                            KAKASI_INSTANCE.setMode('J', 'H')
                            kakasi_converter = KAKASI_INSTANCE.getConverter()
                            if (translated_category_romaji
                                    != translated_category):
                                translated_categories.append(
                                    translated_category_romaji)
                self._add_to_emoji_dict(
                    (emoji_string, language),
                    'categories', translated_categories)

    def _load_cldr_annotation_data(self, language, subdir):
        '''
        Loads translations of emoji names and keywords.

        Translations are loaded from the annotation data from CLDR.
        '''
        dirnames = (USER_DATADIR, DATADIR,
                    # On Fedora >= 25 there is a
                    # “cldr-emoji-annotation” package which has the
                    # .xml files here in the subdirs “annotations”
                    # and “annotationsDerived”:
                    '/usr/share/unicode/cldr/common/',
                    '/local/mfabian/src/cldr-svn/trunk/common/')
        basenames = (language + '.xml',)
        (path, open_function) = _find_path_and_open_function(
            dirnames, basenames, subdir=subdir)
        if not path:
            return
        # change language to the language of the file which was really
        # found (For example, it could be that 'es_ES' was requested,
        # but only the fallback 'es' was really found):
        language = os.path.basename(
            path).replace('.gz', '').replace('.xml', '')
        with open_function(path, mode='rt') as cldr_annotation_file:
            pattern = re.compile(
                r'.*<annotation cp="(?P<emojistring>[^"]+)"'
                +r'\s*(?P<tts>type="tts"){0,1}'
                +r'[^>]*>'
                +r'(?P<content>.+)'
                +r'</annotation>.*'
            )
            for line in cldr_annotation_file.readlines():
                match = pattern.match(line)
                if match:
                    emoji_string = match.group('emojistring')
                    content = html.unescape(match.group('content'))
                    if language.startswith('en'):
                        content = content.lower()
                    if match.group('tts'):
                        if (language in ('zh', 'zh_Hant')
                                and IMPORT_PINYIN_SUCCESSFUL):
                            self._add_to_emoji_dict(
                                (emoji_string, language),
                                'names',
                                [content,
                                 pinyin.get(content)]
                            )
                        elif (language == 'ja' and IMPORT_PYKAKASI_SUCCESSFUL):
                            KAKASI_INSTANCE.setMode('H', 'H')
                            KAKASI_INSTANCE.setMode('K', 'H')
                            KAKASI_INSTANCE.setMode('J', 'H')
                            kakasi_converter = KAKASI_INSTANCE.getConverter()
                            self._add_to_emoji_dict(
                                (emoji_string, language),
                                'names',
                                [content,
                                 kakasi_converter.do(content)]
                            )
                            if self._romaji:
                                KAKASI_INSTANCE.setMode('H', 'a')
                                KAKASI_INSTANCE.setMode('K', 'a')
                                KAKASI_INSTANCE.setMode('J', 'a')
                                # default: use Hepburn Roman table
                                KAKASI_INSTANCE.setMode('r', 'Hepburn')
                                # add space default: no Separator
                                KAKASI_INSTANCE.setMode('C', True)
                                # capitalize default: no Capitalize
                                KAKASI_INSTANCE.setMode('c', False)
                                kakasi_converter = KAKASI_INSTANCE.getConverter()
                                self._add_to_emoji_dict(
                                    (emoji_string, language),
                                    'names',
                                    [content,
                                     kakasi_converter.do(content).lower()]
                                )
                        else:
                            self._add_to_emoji_dict(
                                (emoji_string, language),
                                'names',
                                [content]
                            )
                    else:
                        if (language in ('zh', 'zh_Hant')
                                and IMPORT_PINYIN_SUCCESSFUL):
                            for x in content.split('|'):
                                keyword = x.strip()
                                keyword_pinyin = pinyin.get(keyword)
                                self._add_to_emoji_dict(
                                    (emoji_string, language),
                                    'keywords',
                                    [keyword, keyword_pinyin]
                                )
                        elif (language == 'ja' and IMPORT_PYKAKASI_SUCCESSFUL):
                            KAKASI_INSTANCE.setMode('H', 'H')
                            KAKASI_INSTANCE.setMode('K', 'H')
                            KAKASI_INSTANCE.setMode('J', 'H')
                            kakasi_converter = KAKASI_INSTANCE.getConverter()
                            for x in content.split('|'):
                                keyword = x.strip()
                                keyword_hiragana = kakasi_converter.do(keyword)
                                self._add_to_emoji_dict(
                                    (emoji_string, language),
                                    'keywords',
                                    [keyword, keyword_hiragana]
                                )
                            if self._romaji:
                                KAKASI_INSTANCE.setMode('H', 'a')
                                KAKASI_INSTANCE.setMode('K', 'a')
                                KAKASI_INSTANCE.setMode('J', 'a')
                                # default: use Hepburn Roman table
                                KAKASI_INSTANCE.setMode('r', 'Hepburn')
                                # add space default: no Separator
                                KAKASI_INSTANCE.setMode('C', True)
                                # capitalize default: no Capitalize
                                KAKASI_INSTANCE.setMode('c', False)
                                kakasi_converter = (
                                    KAKASI_INSTANCE.getConverter())
                                for x in content.split('|'):
                                    keyword = x.strip()
                                    keyword_romaji = kakasi_converter.do(
                                        keyword).lower()
                                    self._add_to_emoji_dict(
                                        (emoji_string, language),
                                        'keywords',
                                        [keyword, keyword_romaji]
                                    )
                        else:
                            self._add_to_emoji_dict(
                                (emoji_string, language),
                                'keywords',
                                [x.strip()
                                 for x in content.split('|')]
                            )

    def _set_seq1(self, string):
        '''Sequence 1 is a label from the emoji data'''
        string = itb_util.remove_accents(string).lower()
        self._string1 = string
        if not self._quick:
            # only needed when using SequenceMatcher()
            string = ' ' + string + ' '
            self._seq1 = string
            self._len1 = len(string)
            self._matcher.set_seq1(string)

    def _set_seq2(self, string):
        '''Sequence 2 is the query string, i.e. the user input'''
        string = itb_util.remove_accents(string).lower()
        self._string2 = string
        # Split the input string into a list of words:
        word_list = []
        original_words = string.split(sep=None)
        self._string2_number_of_words = len(original_words)
        for word in original_words:
            word_list += [word]
            # If a word in the input string is not correctly spelled
            # in any of the enabled dictionaries, add spell checking
            # suggestions to the list (don’t do that it it is spelled
            # correctly in at least one dictionary):
            if len(word) > 3 and IMPORT_ENCHANT_SUCCESSFUL:
                spelled_correctly = False
                for dic in self._enchant_dicts:
                    if dic.check(word) or dic.check(word.title()):
                        spelled_correctly = True
                if not spelled_correctly: # incorrect in *all* dictionaries
                    wlist = []
                    for dic in self._enchant_dicts:
                        # don’t use spellchecking suggestions shorter then
                        # 3 characters and lower case everything
                        wlist += [
                            x.lower() for x in dic.suggest(word) if len(x) > 2]
                    # remove possible duplicates from spellchecking
                    word_list += set(wlist)
        # Keep duplicates coming from the query string.
        # Sort longest words first.
        self._string2_word_list = sorted(word_list, key=lambda x: -len(x))
        if not self._quick:
            # only needed when using SequenceMatcher()
            string = ' ' + string + ' '
            self._seq2 = string
            self._len2 = len(string)
            self._matcher.set_seq2(string)
            self._match_cache = {}

    def _match(self, label, debug=False):
        '''Matches a label from the emoji data against the query string.

        The query string must have been already set with
        self._set_seq2(query_string) before calling self._match().

        '''
        self._set_seq1(label)
        total_score = 0
        if debug:
            print('string1 = “%s” string2 = “%s” string2_word_list = “%s”'
                  %(self._string1, self._string2, self._string2_word_list))
        if (self._string1, self._string2) in self._match_cache:
            # Many keywords are of course shared by many emoji,
            # therefore the query string is often matched against
            # labels already matched previously. Caching previous
            # matches speeds it up quite a bit.
            total_score = self._match_cache[(self._string1, self._string2)]
            if debug:
                print('Cached, total_score = %s' %total_score)
            return total_score
        # Does the complete query string match exactly?
        if self._string1 == self._string2:
            if debug:
                print('Exact match, total_score += 1000')
            total_score += 1000
        # Does a word in the query string match exactly?
        for word in set(self._string2_word_list):
            # use set() here to avoid making an exact match stronger
            # just because a word happens to be twice in the input.
            if word == self._string1:
                if self._string2_number_of_words == 1:
                    total_score += 300
                    if debug:
                        print('Spell check exact match, word = “%s”, '
                              %word + 'total_score += 300')
                else:
                    total_score += 200
                    if debug:
                        print('Exact match from word_list, word = “%s”, '
                              %word + 'total_score += 200')
        # Does a word in the query string match the beginning of a word in
        # the label?
        tmp = self._string1
        for word in self._string2_word_list:
            match = re.search(r'\b' + re.escape(word), tmp)
            if match:
                match_value = 100 + match.end() - match.start()
                if match.start() == 0:
                    match_value += 20
                total_score += match_value
                tmp = tmp[:match.start()] + tmp[match.end():]
                if debug:
                    print('Substring match from word_list, word = “%s”, '
                          %word
                          + 'total_score += %s' %match_value)
        # Does a word in the query string match the label if spaces in
        # the label are ignored?
        tmp = self._string1.replace(' ', '')
        for word in self._string2_word_list:
            match = re.search(re.escape(word), tmp)
            if match:
                match_value = 20 + match.end() - match.start()
                if match.start() == 0:
                    match_value += 20
                total_score += match_value
                tmp = tmp[:match.start()] + tmp[match.end():]
                if debug:
                    print('Space insensitive substring match from word_list, '
                          + 'word = “%s”, ' %word
                          + 'total_score += %s' %match_value)
        if self._quick:
            self._match_cache[(self._string1, self._string2)] = total_score
            return total_score
        # The following code using SequenceMatcher() might increase
        # the total_score by up to 500 approximately. It improves
        # the matching a little bit but it is very slow.
        if debug:
            print('seq1 = “%s” seq2 = “%s”' %(self._seq1, self._seq2))
        for tag, i1, i2, j1, j2 in self._matcher.get_opcodes():
            score = 0
            if tag in ('replace', 'delete', 'insert'):
                pass
            if tag == 'equal':
                match_length = i2 - i1
                if match_length > 1:
                    score += match_length
                    # favor word boundaries
                    if self._seq1[i1] == ' ':
                        if i1 == 0 and j1 == 0:
                            score += 4 * match_length
                        elif i1 == 0 or j1 == 0:
                            score += 2 * match_length
                        else:
                            score += match_length
                    if i1 > 0 and j1 > 0 and self._seq1[i1 - 1] == ' ':
                        score += match_length
                    if self._seq1[i2 - 1] == ' ':
                        if i2 == self._len1 and j2 == self._len2:
                            score += 4 * match_length
                        elif i2 == self._len1 or j2 == self._len2:
                            score += 2 * match_length
                        else:
                            score += match_length
            total_score += score
            if debug:
                print(
                    '{:7} a[{:2}:{:2}] --> b[{:2}:{:2}]'.format(
                        tag, i1, i2, j1, j2)
                    + '{:3} {:3} {!r} --> {!r}'.format(
                        score, total_score,
                        self._seq1[i1:i2], self._seq2[j1:j2]))
        self._match_cache[(self._string1, self._string2)] = total_score
        return total_score

    def candidates(self, query_string, match_limit=20, debug=tuple()):
        '''
        Find a list of emoji which best match a query string.

        :param query_string: A search string
        :type query_string: string
        :param match_limit: Limit the number of matches to this amount
        :type match_limit: integer
        :param debug: List or tuple of emojis to print debug information
                      about the matching to stdout.
        :type debug: List of strings
        :rtype: A list of tuples of the form (<emoji>, <name>, <score),
                i.e. a list like this:
                [('🎂', 'birthday cake', 3106), ...]

        Examples:

        >>> mq = EmojiMatcher(languages = ['en_US', 'it_IT', 'es_MX', 'es_ES', 'de_DE', 'ja_JP'])

        >>> mq.candidates('😺', match_limit=3)
        [('😺', 'smiling cat face with open mouth [😺, So, people, cat, face, mouth, open, smile, grinning cat face]', 9), ('😆', 'smiling face with open mouth and tightly-closed eyes [So, people, face, mouth, open, smile]', 6), ('😄', 'smiling face with open mouth and smiling eyes [So, people, face, mouth, open, smile]', 6)]

        >>> mq.candidates('ネコ＿')[0][:2]
        ('🐈', 'ネコ')

        >>> mq.candidates('ant')[0][:2]
        ('🐜', 'ant')

        >>> mq.candidates('ameise')[0][:2]
        ('🐜', 'Ameise')

        >>> mq.candidates('Ameise')[0][:2]
        ('🐜', 'Ameise')

        >>> mq.candidates('formica')[0][:2]
        ('🐜', 'formica')

        >>> mq.candidates('hormiga')[0][:2]
        ('🐜', 'hormiga')

        >>> mq.candidates('cacca')[0][:2]
        ('💩', 'cacca')

        >>> mq.candidates('orso')[0][:2]
        ('🐻', 'faccina orso')

        >>> mq.candidates('lupo')[0][:2]
        ('🐺', 'faccina lupo')

        >>> mq.candidates('gatto')[0][:2]
        ('🐈', 'gatto')

        >>> mq.candidates('gatto sorride')[0][:2]
        ('😺', 'gatto che sorride')

        Any white space and '_' can be used to separate keywords in the
        query string:

        >>> mq.candidates('gatto_	 sorride')[0][:2]
        ('😺', 'gatto che sorride')

        >>> mq.candidates('nerd glasses')[0][:2]
        ('🤓', 'nerd face')

        >>> mq.candidates('smiling face sun glasses')[0][:2]
        ('😎', 'smiling face with sunglasses')

        >>> mq.candidates('halo')[0][:2]
        ('😇', 'smiling face with halo')

        >>> mq.candidates('factory')[0][:2]
        ('🏭', 'factory')

        >>> mq.candidates('man tone5')[0][:2]
        ('👨🏿', 'man: dark skin tone “man tone5”')

        >>> mq.candidates('tone')[0][:2]
        ('🕵🏻', 'detective: light skin tone “sleuth or spy tone1”')

        >>> mq.candidates('tone1')[0][:2]
        ('🏻', 'emoji modifier fitzpatrick type-1-2 “tone1”')

        >>> mq.candidates('tone5')[0][:2]
        ('🏿', 'emoji modifier fitzpatrick type-6 “tone5”')

        >>> mq.candidates('a')[0][:2]
        ('🅰\ufe0f', 'negative squared latin capital letter a')

        >>> mq.candidates('squared a')[0][:2]
        ('🅰\ufe0f', 'negative squared latin capital letter a')

        >>> mq.candidates('squared capital a')[0][:2]
        ('🅰\ufe0f', 'negative squared latin capital letter a')

        >>> mq.candidates('c')[0][:2]
        ('©\ufe0f', 'Copyright')

        >>> mq.candidates('us')[0][:2]
        ('🇺🇸', 'united states “us”')

        >>> mq.candidates('flag us')[0][:2]
        ('🇺🇸', 'united states “us” [flag]')

        >>> mq.candidates('united states')[0][:2]
        ('🇺🇸', 'united states')

        >>> mq.candidates('united')[0][:2]
        ('🇦🇪', 'united arab emirates')

        >>> mq.candidates('united minor outlying islands')[0][:2]
        ('🇺🇲', 'u.s. outlying islands')

        >>> mq.candidates('united arab')[0][:2]
        ('🇦🇪', 'united arab emirates')

        >>> mq.candidates('mm')[0][:2]
        ('🇲🇲', 'myanmar (burma) “mm”')

        >>> mq.candidates('flag mm')[0][:2]
        ('🇲🇲', 'myanmar (burma) “mm” [flag]')

        >>> mq.candidates('myanmar')[0][:2]
        ('🇲🇲', 'Myanmar')

        >>> mq.candidates('sj')[0][:2]
        ('🇸🇯', 'svalbard & jan mayen “sj”')

        >>> mq.candidates('flag sj')[0][:2]
        ('🇸🇯', 'svalbard & jan mayen “sj” [flag]')

        >>> mq.candidates('svalbard')[0][:2]
        ('🇸🇯', 'Svalbard e Jan Mayen')

        >>> mq.candidates('jan mayen')[0][:2]
        ('🇸🇯', 'Spitzbergen und Jan Mayen')

        >>> mq.candidates('mayen')[0][:2]
        ('🇸🇯', 'Spitzbergen und Jan Mayen')

        >>> mq.candidates(':-)')[0][:2]
        ('🙂', 'slightly smiling face “:-)”')

        >>> mq.candidates('family')[0][:2]
        ('👪', 'family')

        >>> mq.candidates('man')[0][:2]
        ('👨', 'man')

        >>> mq.candidates('woman')[0][:2]
        ('👩', 'woman')

        >>> mq.candidates('girl')[0][:2]
        ('👧', 'girl')

        >>> mq.candidates('boy')[0][:2]
        ('👦', 'boy')

        >>> mq.candidates('family man')[0][:2]
        ('👨\u200d👩\u200d👦', 'family: man, woman, boy “family man woman boy”')

        >>> mq.candidates('man man girl boy')[0][:2]
        ('👨\u200d👧\u200d👦', 'family: man, girl, boy “family man girl boy”')

        >>> mq.candidates('mmgb')[0][:2]
        ('👨\u200d👨\u200d👧\u200d👦', 'family: man, man, girl, boy “family mmgb”')

        >>> mq.candidates('manmangirlboy')[0][:2]
        ('👨\u200d👨\u200d👧\u200d👦', 'family: man, man, girl, boy')

        >>> mq.candidates('bird')[0][:2]
        ('🐦', 'bird')

        >>> mq.candidates('bir')[0][:2]
        ('🎂', 'birthday cake')

        >>> mq.candidates('birth')[0][:2]
        ('🎂', 'birthday cake')

        >>> mq.candidates('camera')[0][:2]
        ('📷', 'camera')

        >>> mq.candidates('symbol')[0][:2]
        ('🔣', 'input symbol for symbols {Symbol}')

        >>> mq.candidates('atomsymbol')[0][:2]
        ('⚛\ufe0f', 'atom symbol')

        >>> mq.candidates('peacesymbol')[0][:2]
        ('☮\ufe0f', 'peace symbol')

        >>> mq.candidates('peace symbol')[0][:2]
        ('☮\ufe0f', 'peace symbol {Symbol}')

        >>> mq.candidates('animal')[0][:2]
        ('🐵', 'cara de mono [animal]')

        >>> mq.candidates('dromedary animal')[0][:2]
        ('🐪', 'dromedary camel')

        >>> mq.candidates('camel')[0][:2]
        ('🐫', 'bactrian camel')

        >>> mq.candidates('people')[0][:2]
        ('👯', 'woman with bunny ears “people with bunny ears”')

        >>> mq.candidates('nature')[0][:2]
        ('🙈', 'see-no-evil monkey {nature}')

        >>> mq.candidates('travel')[0][:2]
        ('🏎️', 'racing car {travel}')

        >>> mq.candidates('ferry')[0][:2]
        ('⛴\ufe0f', 'ferry')

        >>> mq.candidates('ferry travel')[0][:2]
        ('⛴\ufe0f', 'ferry {travel}')

        >>> mq.candidates('ferry travel boat')[0][:2]
        ('⛴\ufe0f', 'ferry {travel}')

        >>> mq.candidates('boat')[0][:2]
        ('🚣🏻\u200d♂️', 'man rowing boat: light skin tone “man rowing boat light skin tone”')

        >>> mq.candidates('anchor')[0][:2]
        ('⚓', 'anchor')

        >>> mq.candidates('anchor boat')[0][:2]
        ('🚣🏻\u200d♂️', 'man rowing boat: light skin tone “man rowing boat light skin tone”')

        >>> mq.candidates('buterfly')[0][:2]
        ('\U0001f98b', 'butterfly')

        >>> mq.candidates('badminton')[0][:2]
        ('🏸', 'badminton racquet and shuttlecock')

        >>> mq.candidates('badmynton')[0][:2]
        ('🏸', 'badminton racquet and shuttlecock')

        >>> mq.candidates('padminton')[0][:2]
        ('🏸', 'badminton racquet and shuttlecock')

        >>> mq.candidates('fery')[0][:2]
        ('⛴\ufe0f', 'ferry')

        >>> mq.candidates('euro sign')[0][:2]
        ('€', 'euro sign')

        >>> mq.candidates('superscript one')[0][:2]
        ('¹', 'superscript one')

        >>> mq.candidates('currency')[0][:2]
        ('💱', 'currency exchange')

        >>> mq.candidates('connector')[0][:2]
        ('﹎', 'centreline low line {Connector}')

        >>> mq.candidates('dash')[0][:2]
        ('💨', 'dash symbol')

        >>> mq.candidates('close')[0][:2]
        ('⸥', 'bottom right half bracket {Close}')

        >>> mq.candidates('punctuation')[0][:2]
        ('‼\ufe0f', 'double exclamation mark {Punctuation} [punctuation]')

        >>> mq.candidates('final quote')[0][:2]
        ('⸅', 'right dotted substitution bracket {Final quote}')

        >>> mq.candidates('initial quote')[0][:2]
        ('‟', 'double high-reversed-9 quotation mark {Initial quote}')

        >>> mq.candidates('modifier')[0][:2]
        ('🏻', 'emoji modifier fitzpatrick type-1-2 {Modifier}')

        >>> mq.candidates('math')[0][:2]
        ('𝜵', 'mathematical bold italic nabla {Math}')

        >>> mq.candidates('separator line')[0][:2]
        (' ', 'U+2028 line separator {Line}')

        >>> mq.candidates('separator paragraph')[0][:2]
        (' ', 'U+2029 paragraph separator {Paragraph}')

        >>> mq.candidates('separator space')[0][:2]
        (' ', 'U+20 space {Space}')

        >>> mq = EmojiMatcher(languages = ['fr_FR'])
        >>> mq.candidates('chat')[0][:2]
        ('🐈', 'chat')

        >>> mq.candidates('réflexion')[0][:2]
        ('🤔', 'visage en pleine réflexion')

        >>> mq.candidates('🤔', match_limit = 3)
        [('🤔', 'visage en pleine réflexion [🤔, réflexion, visage, visage en pleine réflexion]', 4), ('🤩', 'visage avec des étoiles à la place des yeux [visage]', 1), ('🤗', 'visage qui fait un câlin [visage]', 1)]

        >>> mq = EmojiMatcher(languages = ['fr_FR'])
        >>> mq.candidates('2019')
        [('’', 'U+2019 right single quotation mark', 200)]

        >>> mq.candidates('41')
        [('A', 'U+41 latin capital letter a', 200)]

        >>> mq.candidates('2a')
        [('*', 'U+2A asterisk', 200)]

        >>> mq.candidates('1b')
        [('\\x1b', 'U+1B', 200)]

        >>> mq.candidates('')
        []
        '''
        if not query_string:
            return []
        # self._emoji_dict contains only non-fully-qualified sequences:
        query_string = self.variation_selector_16_normalize(
            query_string, non_fully_qualified=True)
        # Replace any sequence of white space characters and '_'
        # and '＿' in the query string with a single ' '.  '＿'
        # (U+FF3F FULLWIDTH LOW LINE) is included here because when
        # Japanese transliteration is used, something like “neko_”
        # transliterates to “ねこ＿” and that should of course match
        # the emoji for “ねこ”　(= “cat”):
        query_string = re.sub(r'[＿_\s]+', ' ', query_string)
        if ((query_string, match_limit) in self._candidate_cache
                and not debug):
            return self._candidate_cache[(query_string, match_limit)]
        if (query_string, 'en') in self._emoji_dict:
            # the query_string is itself an emoji, match similar ones:
            candidates = self.similar(query_string, match_limit=match_limit)
            self._candidate_cache[(query_string, match_limit)] = candidates
            return candidates
        self._set_seq2(query_string)
        candidates = []
        for emoji_key, emoji_value in self._emoji_dict.items():
            if emoji_key[0] in debug:
                debug_match = True
                print('===================================')
                print('Debug match for “%s”' %emoji_key[0])
                print('===================================')
            else:
                debug_match = False

            total_score = 0
            good_match_score = 200
            name_good_match = ''
            ucategory_good_match = ''
            category_good_match = ''
            keyword_good_match = ''
            if 'names' in emoji_value:
                for name in emoji_value['names']:
                    score = 2 * self._match(name, debug=debug_match)
                    if score >= good_match_score:
                        name_good_match = name
                    total_score += score
            if 'ucategories' in emoji_value:
                for ucategory in emoji_value['ucategories']:
                    score = self._match(ucategory, debug=debug_match)
                    if score >= good_match_score:
                        ucategory_good_match = ucategory
                    total_score += score
            if 'categories' in emoji_value:
                for category in emoji_value['categories']:
                    score = self._match(category, debug=debug_match)
                    if score >= good_match_score:
                        category_good_match = category
                    total_score += score
            if 'keywords' in emoji_value:
                for keyword in emoji_value['keywords']:
                    score = self._match(keyword, debug=debug_match)
                    if score >= good_match_score:
                        keyword_good_match = keyword
                    total_score += score

            if total_score > 0:
                if 'names' in emoji_value:
                    display_name = emoji_value['names'][0]
                else:
                    display_name = self.name(emoji_key[0])
                if (len(emoji_key[0]) == 1
                        and is_invisible(emoji_key[0])):
                    # Add the code point to the display name of
                    # “invisible” characters:
                    display_name = ('U+%X' %ord(emoji_key[0])
                                    + ' ' + display_name)
                # If the match was good because something else
                # but the main name had a good match, show it in
                # the display name to make the user understand why
                # this emoji matched:
                if name_good_match not in display_name:
                    display_name += ' “' + name_good_match + '”'
                if ucategory_good_match not in display_name:
                    display_name += ' {' + ucategory_good_match + '}'
                if category_good_match not in display_name:
                    display_name += ' {' + category_good_match + '}'
                if keyword_good_match not in display_name:
                    display_name += ' [' + keyword_good_match + ']'
                candidates.append((
                    self.variation_selector_16_normalize(
                        emoji_key[0],
                        self._non_fully_qualified),
                    display_name,
                    total_score))

        try:
            codepoint = int(query_string, 16)
            if (codepoint >= 0x0 and codepoint <= 0x1FFFFF
                # exclude surrogates and private use characters:
                and not (codepoint >= 0xd800 and codepoint <= 0xf8ff)
                and not (codepoint >= 0xf0000 and codepoint <= 0xffffd)
                and not (codepoint >= 0x100000 and codepoint <= 0x10fffd)):
                char = chr(codepoint)
                name = self.name(char)
                if not name:
                    try:
                        name = unicodedata.name(char).lower()
                    except (ValueError,):
                        pass
                if name:
                    name = ' ' + name
                candidates.append(
                    (char,
                     'U+' + query_string.upper()
                     + name,
                     good_match_score))
        except (ValueError,):
            pass

        sorted_candidates = sorted(
            candidates,
            key=lambda x: (
                - x[2],                # score
                self.cldr_order(x[0]), # CLDR order
                - len(x[0]),           # length of the emoji sequence
                x[1]                   # name of the emoji
            ))[:match_limit]

        self._candidate_cache[(query_string, match_limit)] = sorted_candidates
        return sorted_candidates

    def names(self, emoji_string, language=''):
        '''Find the names of an emoji

        Returns a list of names of the emoji in the language requested
        or and empty list if no name can be found in that language.

        If no language is requested, the list of names is returned in
        the first language of this EmojiMatcher for which a list of
        names can be found.

        :param emoji_string: The string of Unicode characters which are
                             used to encode the emoji
        :type emoji_string: string
        :param language: The language requested for the name
        :type language: string
        :rtype: List of strings

        Examples:

        >>> matcher = EmojiMatcher(languages = ['en_US', 'it_IT', 'es_MX', 'es_ES', 'de_DE', 'ja_JP'])
        >>> matcher.names('🙂')
        ['slightly smiling face', 'slight smile', ':)', ':-)', '=]', '=)', ':]']
        '''
        # self._emoji_dict contains only non-fully-qualified sequences:
        emoji_string = self.variation_selector_16_normalize(
            emoji_string, non_fully_qualified=True)
        if language:
            if ((emoji_string, language) in self._emoji_dict
                    and 'names' in self._emoji_dict[(emoji_string, language)]):
                return self._emoji_dict[(emoji_string, language)]['names']
            else:
                return []
        for language in expand_languages(self._languages):
            if ((emoji_string, language) in self._emoji_dict
                    and 'names' in self._emoji_dict[(emoji_string, language)]):
                return self._emoji_dict[(emoji_string, language)]['names']
        return []

    def name(self, emoji_string, language=''):
        '''Find the main name of an emoji.

        Returns a name of the emoji in the language requested
        or and empty string if no name can be found in that language.

        If no language is requested, the name is returned in the first
        language of this EmojiMatcher for which a name can be
        found.

        :param emoji_string: The string of Unicode characters which are
                             used to encode the emoji
        :type emoji_string: string
        :param language: The language requested for the name
        :type language: string
        :rtype: string

        Examples:

        >>> matcher = EmojiMatcher(languages = ['en_US', 'it_IT', 'es_MX', 'es_ES', 'de_DE', 'ja_JP'])

        >>> matcher.name('🏸')
        'badminton racquet and shuttlecock'

        >>> matcher.name('🖥')
        'desktop computer'

        >>> matcher = EmojiMatcher(languages=['es_MX', 'es_ES', 'it_IT', 'ja_JP'])
        >>> matcher.name('🖥')
        'computadora de escritorio'

        >>> matcher = EmojiMatcher(languages=['es_ES', 'es_MX', 'it_IT', 'ja_JP'])
        >>> matcher.name('🖥')
        'ordenador de sobremesa'

        >>> matcher = EmojiMatcher(languages=['de_DE', 'es_ES', 'es_MX', 'it_IT', 'ja_JP'])
        >>> matcher.name('🖥')
        'Desktopcomputer'

        >>> matcher = EmojiMatcher(languages=['it_IT', 'es_ES', 'es_MX', 'ja_JP'])
        >>> matcher.name('🖥')
        'desktop PC'

        >>> matcher = EmojiMatcher(languages=['fr_FR'])
        >>> matcher.name('🖥')
        'ordinateur de bureau'

        >>> matcher.name('🤔')
        'visage en pleine réflexion'

        >>> matcher = EmojiMatcher(languages=['de_DE'])
        >>> matcher.name('🤔')
        'nachdenkendes Gesicht'

        >>> matcher.name('⚽')
        'Fußball'

        >>> matcher = EmojiMatcher(languages=['de_CH'])
        >>> matcher.name('🤔')
        'nachdenkendes Gesicht'

        >>> matcher.name('⚽')
        'Fussball'

        >>> matcher.name('a')
        ''

        >>> matcher.name(' ')
        'space'
        '''
        names = self.names(emoji_string, language=language)
        if names:
            return names[0]
        else:
            return ''

    def keywords(self, emoji_string, language=''):
        '''Return the keywords of an emoji

        Returns a list of keywords of the emoji in the language requested
        or and empty list if no keywords can be found in that language.

        If no language is requested, the list of keywords is returned in
        the first language of this EmojiMatcher for which a list of
        keywords can be found.

        :param emoji_string: The string of Unicode characters which are
                             used to encode the emoji
        :type emoji_string: string
        :param language: The language requested for the name
        :type language: string
        :rtype: List of strings

        Examples:

        >>> matcher = EmojiMatcher(languages = ['en_US', 'it_IT', 'es_MX', 'es_ES', 'de_DE', 'ja_JP'])
        >>> matcher.keywords('🙂')
        ['face', 'smile', 'slightly smiling face']

        >>> matcher.keywords('🙂', language='it')
        ['faccina con sorriso accennato', 'mezzo sorriso', 'sorriso', 'sorriso a bocca chiusa']
        '''
        # self._emoji_dict contains only non-fully-qualified sequences:
        emoji_string = self.variation_selector_16_normalize(
            emoji_string, non_fully_qualified=True)
        if language:
            if ((emoji_string, language) in self._emoji_dict
                    and 'keywords' in self._emoji_dict[(emoji_string, language)]):
                return self._emoji_dict[(emoji_string, language)]['keywords']
            else:
                return []
        for language in expand_languages(self._languages):
            if ((emoji_string, language) in self._emoji_dict
                    and 'keywords' in self._emoji_dict[(emoji_string, language)]):
                return self._emoji_dict[(emoji_string, language)]['keywords']
        return []

    def categories(self, emoji_string, language=''):
        '''Return the categories of an emoji

        Returns a list of categories of the emoji in the language requested
        or and empty list if no categories can be found in that language.

        If no language is requested, the list of categories is returned in
        the first language of this EmojiMatcher for which a list of
        categories can be found.

        :param emoji_string: The string of Unicode characters which are
                             used to encode the emoji
        :type emoji_string: string
        :param language: The language requested for the name
        :type language: string
        :rtype: List of strings

        Examples:

        >>> matcher = EmojiMatcher(languages = ['en_US', 'it_IT', 'es_MX', 'es_ES', 'de_DE', 'ja_JP'])
        >>> matcher.categories('🙂')
        ['people']
        '''
        # self._emoji_dict contains only non-fully-qualified sequences:
        emoji_string = self.variation_selector_16_normalize(
            emoji_string, non_fully_qualified=True)
        if language:
            if ((emoji_string, language) in self._emoji_dict
                    and 'categories' in self._emoji_dict[(emoji_string, language)]):
                return self._emoji_dict[(emoji_string, language)]['categories']
            else:
                return []
        for language in expand_languages(self._languages):
            if ((emoji_string, language) in self._emoji_dict
                    and 'categories' in self._emoji_dict[(emoji_string, language)]):
                return self._emoji_dict[(emoji_string, language)]['categories']
        return []

    def similar(self, emoji_string, match_limit=1000):
        '''Find similar emojis

        “Similar” means they share categories or keywords.

        :param emoji_string: The string of Unicode  characters which are
                             used to encode the emoji
        :type emoji_string: A string
        :rtype: A list of tuples of the form (<emoji>, <name>, <score>),
                i.e. a list like this:

                [('🐫', "cammello ['🐫', 'gobba', 'animale']", 3), ...]

                The name includes the list of categories or keywords
                which matched, the score is the number of categories
                or keywords matched.

                The list is sorted by preferred language, then score,
                then name.

        Examples:

        >>> matcher = EmojiMatcher(languages = ['en_US', 'it_IT', 'es_MX', 'es_ES', 'de_DE', 'ja_JP'])

        >>> matcher.similar('this is not an emoji', match_limit = 5)
        []

        >>> matcher.similar('☺', match_limit = 5)
        [('☺️', 'white smiling face [☺️, So, people, face, outlined, relaxed, smile, smiling face]', 8), ('🙂', 'slightly smiling face [So, people, face, smile]', 4), ('😙', 'kissing face with smiling eyes [So, people, face, smile]', 4), ('😍', 'smiling face with heart-shaped eyes [So, people, face, smile]', 4), ('😎', 'smiling face with sunglasses [So, people, face, smile]', 4)]

        >>> matcher = EmojiMatcher(languages = ['it_IT', 'en_US', 'es_MX', 'es_ES', 'de_DE', 'ja_JP'])
        >>> matcher.similar('☺', match_limit = 5)
        [('☺️', 'faccina sorridente [☺️, contorno faccina sorridente, emozionarsi, faccina, sorridente]', 5), ('😺', 'gatto che sorride [faccina, sorridente]', 2), ('😚', 'faccina che bacia con occhi chiusi [faccina]', 1), ('😙', 'faccina che bacia con occhi sorridenti [faccina]', 1), ('🤗', 'faccina che abbraccia [faccina]', 1)]

        >>> matcher = EmojiMatcher(languages = ['en_US', 'it_IT', 'es_MX', 'es_ES', 'de_DE', 'ja_JP'])
        >>> matcher.similar('🐫', match_limit = 5)
        [('🐫', 'bactrian camel [🐫, bactrian, camel, hump, two humps, two-hump camel]', 6), ('🐪', 'dromedary camel [camel, hump]', 2), ('🐫', 'bactrian camel [🐫, So, nature, bactrian, camel, hump, two-hump camel]', 7), ('🐪', 'dromedary camel [So, nature, hump, camel]', 4), ('\U0001f999', 'llama [So, nature]', 2)]

        >>> matcher = EmojiMatcher(languages = [ 'it_IT', 'en_US','es_MX', 'es_ES', 'de_DE', 'ja_JP'])
        >>> matcher.similar('🐫', match_limit = 5)
        [('🐫', 'cammello [🐫, animale, cammello, gobba]', 4), ('🐪', 'dromedario [animale, cammello, gobba]', 3), ('🐐', 'capra [animale]', 1), ('🐑', 'pecora [animale]', 1), ('🐘', 'elefante [animale]', 1)]

        >>> matcher = EmojiMatcher(languages = ['de_DE', 'it_IT', 'en_US','es_MX', 'es_ES', 'ja_JP'])
        >>> matcher.similar('🐫', match_limit = 5)
        [('🐫', 'Kamel [🐫, Kamel, Tier, zweihöckrig]', 4), ('🐪', 'Dromedar [Kamel, Tier]', 2), ('🐐', 'Ziege [Tier]', 1), ('🐑', 'Schaf [Tier]', 1), ('🐘', 'Elefant [Tier]', 1)]

        >>> matcher = EmojiMatcher(languages = ['es_MX', 'it_IT', 'de_DE', 'en_US', 'es_ES', 'ja_JP'])
        >>> matcher.similar('🐫', match_limit = 5)
        [('🐫', 'camello [🐫, animal, joroba]', 3), ('🐪', 'dromedario [animal, joroba]', 2), ('🐐', 'cabra [animal]', 1), ('🐑', 'oveja [animal]', 1), ('🐘', 'elefante [animal]', 1)]

        >>> matcher = EmojiMatcher(languages = ['es_ES',  'it_IT', 'es_MX', 'de_DE', 'en_US', 'ja_JP'])
        >>> matcher.similar('🐫', match_limit = 5)
        [('🐫', 'camello [🐫, bactriano, camello, desierto, dromedario, jorobas]', 6), ('🐪', 'dromedario [camello, desierto, dromedario]', 3), ('🏜️', 'desierto [desierto]', 1), ('🐫', 'cammello [🐫, animale, cammello, gobba]', 4), ('🐪', 'dromedario [animale, cammello, gobba]', 3)]

        >>> matcher = EmojiMatcher(languages = ['es_ES',  'it_IT', 'es_MX', 'de_DE', 'en_US', 'ja_JP'])
        >>> matcher.similar('€', match_limit = 5)
        [('€', 'euro sign [€, Sc]', 2), ('؋', 'afghani sign [Sc]', 1), ('֏', 'armenian dram sign [Sc]', 1), ('₳', 'austral sign [Sc]', 1), ('৻', 'bengali ganda mark [Sc]', 1)]

        >>> matcher.similar('🏄‍♂', match_limit = 2)
        [('🏄\u200d♂️', 'hombre haciendo surf [🏄\u200d♂️, hombre, hombre haciendo surf, surf, surfero, surfista]', 6), ('🏄🏻\u200d♂️', 'hombre haciendo surf: tono de piel claro [hombre, hombre haciendo surf, surf, surfero, surfista]', 5)]
        '''
        # self._emoji_dict contains only non-fully-qualified sequences:
        emoji_string = self.variation_selector_16_normalize(
            emoji_string, non_fully_qualified=True)
        candidate_scores = {}
        original_labels = {}
        expanded_languages = expand_languages(self._languages)
        label_keys = ('ucategories', 'categories', 'keywords')
        for language in expanded_languages:
            original_labels[language] = set()
            emoji_key = (emoji_string, language)
            if emoji_key not in self._emoji_dict:
                continue
            for label_key in label_keys:
                if label_key in self._emoji_dict[emoji_key]:
                    for label in self._emoji_dict[emoji_key][label_key]:
                        original_labels[language].add(label)
                        if (label_key == 'ucategories'
                                and label in UNICODE_CATEGORIES):
                            # For example, label could be 'So' in this
                            # case.  The next two labels will be
                            # 'Symbol' and 'Other' then. In almost all
                            # cases, adding these as well to
                            # original_labels_for_language would not
                            # change the final result. It would only
                            # add two more strings to the list of
                            # matching labels for *every* similar
                            # emoji. Therefore, it would only make the
                            # candidate list for similar emoji much
                            # wider without giving any extra
                            # information to the user. Better skip
                            # the rest of labels in this case.
                            break
        for similar_key in self._emoji_dict:
            similar_string = similar_key[0]
            language = similar_key[1]
            if 'names' in self._emoji_dict[similar_key]:
                similar_name = self._emoji_dict[similar_key]['names'][0]
            else:
                similar_name = self.name(similar_string)
            if (len(similar_string) == 1
                    and is_invisible(similar_string)):
                # Add the code point to the display name of
                # “invisible” characters:
                similar_name = ('U+%X' %ord(similar_string)
                                + ' ' + similar_name)
            scores_key = (
                similar_string, language, similar_name)
            if similar_string == emoji_string:
                # This is exactly the same emoji, add the emoji
                # itself as one extra label.  This way, the
                # original emoji gets a higher score then emoji
                # which share all categories and all keywords.
                # The most similar emoji should always be the
                # original emoji itself.
                candidate_scores[scores_key] = [
                    self.variation_selector_16_normalize(
                        emoji_string,
                        non_fully_qualified=self._non_fully_qualified)]
            for label_key in label_keys:
                if label_key in self._emoji_dict[similar_key]:
                    for label in self._emoji_dict[similar_key][label_key]:
                        if label in original_labels[language]:
                            if scores_key in candidate_scores:
                                candidate_scores[scores_key].append(label)
                            else:
                                candidate_scores[scores_key] = [label]
        candidates = []
        cldr_order_emoji_string = self.cldr_order(emoji_string)
        for x in sorted(candidate_scores.items(),
                        key=lambda x: (
                            expanded_languages.index(x[0][1]), # language index
                            - len(x[1]), # number of matching labels
                            # abs(difference in cldr_order):
                            + abs(self.cldr_order(x[0][0]) - cldr_order_emoji_string),
                            self.cldr_order(x[0][0]), # CLDR order
                            - len(x[0][0]), # length of emoji string
                            x[0][2], # emoji name
                        ))[:match_limit]:
            emoji = self.variation_selector_16_normalize(
                x[0][0],
                non_fully_qualified=self._non_fully_qualified)
            name = x[0][2] + ' [' + ', '.join(x[1]) + ']'
            score = len(x[1])
            candidates.append((emoji, name, score))
        return candidates

    def emoji_by_label(self):
        '''
        :rtype:
        '''
        label_keys = ('ucategories', 'categories', 'keywords', 'names')
        emoji_by_label_dict = {}
        for label_key in label_keys:
            for emoji_key, emoji_value in self._emoji_dict.items():
                emoji = self.variation_selector_16_normalize(
                    emoji_key[0],
                    non_fully_qualified=self._non_fully_qualified)
                unicode_version  = self.unicode_version(emoji)
                if (unicode_version
                        and (LooseVersion(unicode_version)
                             < LooseVersion(self._emoji_unicode_min)
                             or LooseVersion(unicode_version)
                             > LooseVersion(self._emoji_unicode_max))):
                    continue
                if len(emoji) > 1:
                    has_skin_tone_modifier = False
                    for modifier in SKIN_TONE_MODIFIERS:
                        if modifier in emoji:
                            has_skin_tone_modifier = True
                    if has_skin_tone_modifier:
                        # Skip all emoji which already contain a
                        # skin tone modifier, the skin tone variants
                        # will be created when needed when browsing
                        # the categories in emoji-picker:
                        continue
                language = emoji_key[1]
                if not language in emoji_by_label_dict:
                    emoji_by_label_dict[language] = {}
                if label_key in emoji_value:
                    if not label_key in emoji_by_label_dict[language]:
                        emoji_by_label_dict[language][label_key] = {}
                    if label_key == 'ucategories':
                        ucategory_label_full = ', '.join(
                            emoji_value[label_key])
                        if (not ucategory_label_full
                                in emoji_by_label_dict[language][label_key]):
                            emoji_by_label_dict[
                                language][
                                    label_key][
                                        ucategory_label_full] = [emoji]
                        else:
                            emoji_by_label_dict[
                                language][
                                    label_key][
                                        ucategory_label_full].append(emoji)
                    else:
                        for label in emoji_value[label_key]:
                            if (not label in
                                    emoji_by_label_dict[language][label_key]):
                                emoji_by_label_dict[
                                    language][
                                        label_key][
                                            label] = [emoji]
                            else:
                                emoji_by_label_dict[
                                    language][
                                        label_key][
                                            label].append(emoji)
        for language in emoji_by_label_dict:
            for label_key in emoji_by_label_dict[language]:
                for label in emoji_by_label_dict[language][label_key]:
                    emoji_by_label_dict[language][label_key][label] = sorted(
                        emoji_by_label_dict[language][label_key][label],
                        key=lambda x: (
                            self.cldr_order(x),
                            x,
                        ))
        return emoji_by_label_dict

    def emoji_order(self, emoji_string):
        '''Returns the “emoji_order” number from emojione

        Useful for sorting emoji. For characters which do not
        have an emoji order, 0xffffffff is returned.

        :param emoji_string: An emoji
        :type emoji_string: String
        :rtype: Integer

        Examples:

        >>> matcher = EmojiMatcher(languages = ['en'])
        >>> matcher.emoji_order('😀')
        1

        >>> hex(matcher.emoji_order('∬'))
        '0xffffffff'
        '''
        # self._emoji_dict contains only non-fully-qualified sequences:
        emoji_string = self.variation_selector_16_normalize(
            emoji_string, non_fully_qualified=True)
        if ((emoji_string, 'en') in self._emoji_dict
                and 'emoji_order' in self._emoji_dict[(emoji_string, 'en')]):
            return int(self._emoji_dict[(emoji_string, 'en')]['emoji_order'])
        return 0xFFFFFFFF

    def cldr_order(self, emoji_string):
        '''Returns a “cldr_order” number from CLDR

        Useful for sorting emoji. For characters which do not
        have a “cldr_order” number, 0xffffffff is returned.

        The “cldr_order” number is generated  by parsing
        emoji-test.txt.

        :param emoji_string: An emoji
        :type emoji_string: String
        :rtype: Integer

        Examples:

        >>> matcher = EmojiMatcher(languages = ['en'])
        >>> matcher.cldr_order('😀')
        1

        >>> hex(matcher.cldr_order('∬'))
        '0xffffffff'
        '''
        # self._emoji_dict contains only non-fully-qualified sequences:
        emoji_string = self.variation_selector_16_normalize(
            emoji_string, non_fully_qualified=True)
        if ((emoji_string, 'en') in self._emoji_dict
                and 'cldr_order' in self._emoji_dict[(emoji_string, 'en')]):
            return int(self._emoji_dict[(emoji_string, 'en')]['cldr_order'])
        return 0xFFFFFFFF

    def properties(self, emoji_string):
        '''
        Returns the emoji properties of this emoji from the unicode.org data

        :param emoji_string: An emoji
        :type emoji_string: String
        :rtype: List of strings
        '''
        # self._emoji_dict contains only non-fully-qualified sequences:
        emoji_string = self.variation_selector_16_normalize(
            emoji_string, non_fully_qualified=True)
        if (((emoji_string, 'en') in self._emoji_dict)
            and ('properties' in self._emoji_dict[(emoji_string, 'en')])):
            return self._emoji_dict[(emoji_string, 'en')]['properties']
        else:
            return []

    def unicode_version(self, emoji_string):
        '''
        Returns the Unicode version when this emoji/character was added

        :param emoji_string: An emoji
        :type emoji_string: String
        :rtype: String
        '''
        # self._emoji_dict contains only non-fully-qualified sequences:
        emoji_string = self.variation_selector_16_normalize(
            emoji_string, non_fully_qualified=True)
        if (((emoji_string, 'en') in self._emoji_dict)
            and ('uversion' in self._emoji_dict[(emoji_string, 'en')])):
            return self._emoji_dict[(emoji_string, 'en')]['uversion']
        else:
            return ''

    def skin_tone_modifier_supported(self, emoji_string):
        '''Checks whether skin tone modifiers are possible for this emoji

        Returns True if skin  tone modifiers  are possible
        for this emoji_string, False if not.

        :param emoji_string: The emoji to check
        :type emoji_string: String
        :rtype: Boolean

        Examples:

        >>> matcher = EmojiMatcher(languages = ['en'])
        >>> matcher.skin_tone_modifier_supported('👩')
        True

        >>> matcher.skin_tone_modifier_supported('👩🏻')
        True

        >>> matcher.skin_tone_modifier_supported('👮\u200d♀')
        True

        >>> matcher.skin_tone_modifier_supported('😀')
        False

        >>> matcher.skin_tone_modifier_supported('😀🏻')
        False

        >>> matcher.skin_tone_modifier_supported('')
        False

        >>> matcher.skin_tone_modifier_supported('🏻')
        False
        '''
        if len(self.skin_tone_variants(emoji_string)) > 1:
            return True
        else:
            return False

    def skin_tone_variants(self, emoji_string):
        '''
        Returns a list of skin tone variants for the given emoji

        If the given emoji does not support skin tones, a list
        containing only the original emoji is returned.

        :param emoji_string: The emoji to check
        :type emoji_string: String
        :rtype: List of strings

        Examples:

        >>> matcher = EmojiMatcher(languages = ['en'])
        >>> matcher.skin_tone_variants('👩')
        ['👩', '👩🏻', '👩🏼', '👩🏽', '👩🏾', '👩🏿']

        >>> matcher.skin_tone_variants('👩🏻')
        ['👩', '👩🏻', '👩🏼', '👩🏽', '👩🏾', '👩🏿']

        >>> matcher.skin_tone_variants('👮\u200d♀\ufe0f')
        ['👮\u200d♀\ufe0f', '👮🏻\u200d♀\ufe0f', '👮🏼\u200d♀\ufe0f', '👮🏽\u200d♀\ufe0f', '👮🏾\u200d♀\ufe0f', '👮🏿\u200d♀\ufe0f']

        >>> matcher.skin_tone_variants('👩\u200d🎓')
        ['👩\u200d🎓', '👩🏻\u200d🎓', '👩🏼\u200d🎓', '👩🏽\u200d🎓', '👩🏾\u200d🎓', '👩🏿\u200d🎓']

        >>> matcher.skin_tone_variants('😀')
        ['😀']

        >>> matcher.skin_tone_variants('😀🏿')
        ['😀🏿']

        >>> matcher.skin_tone_variants('')
        ['']

        >>> matcher.skin_tone_variants('🏿')
        ['🏿']

        # Family: woman, girl
        # See: http://unicode.org/Public/emoji/5.0/emoji-zwj-sequences.txt
        # which contains the line:
        #
        # 1F469 200D 1F467; Emoji_ZWJ_Sequence; family: woman, girl # 6.0  [1] (👩‍👧)
        >>> len(matcher.skin_tone_variants('👩\u200d👧'))
        36

        >>> len(matcher.skin_tone_variants('👩🏼\u200d👧🏿'))
        36

        >>> matcher.skin_tone_variants('👩🏼\u200d👧🏿') == matcher.skin_tone_variants('👩\u200d👧')
        True

        >>> matcher.skin_tone_variants('👩\u200d👧')
        ['👩\u200d👧', '👩\u200d👧🏻', '👩\u200d👧🏼', '👩\u200d👧🏽', '👩\u200d👧🏾', '👩\u200d👧🏿', '👩🏻\u200d👧', '👩🏻\u200d👧🏻', '👩🏻\u200d👧🏼', '👩🏻\u200d👧🏽', '👩🏻\u200d👧🏾', '👩🏻\u200d👧🏿', '👩🏼\u200d👧', '👩🏼\u200d👧🏻', '👩🏼\u200d👧🏼', '👩🏼\u200d👧🏽', '👩🏼\u200d👧🏾', '👩🏼\u200d👧🏿', '👩🏽\u200d👧', '👩🏽\u200d👧🏻', '👩🏽\u200d👧🏼', '👩🏽\u200d👧🏽', '👩🏽\u200d👧🏾', '👩🏽\u200d👧🏿', '👩🏾\u200d👧', '👩🏾\u200d👧🏻', '👩🏾\u200d👧🏼', '👩🏾\u200d👧🏽', '👩🏾\u200d👧🏾', '👩🏾\u200d👧🏿', '👩🏿\u200d👧', '👩🏿\u200d👧🏻', '👩🏿\u200d👧🏼', '👩🏿\u200d👧🏽', '👩🏿\u200d👧🏾', '👩🏿\u200d👧🏿']

        >>> len(matcher.skin_tone_variants('👨\u200d👩\u200d👧\u200d👦'))
        1296

        # Woman in lotus position
        # Does support skin tone in http://unicode.org/Public/emoji/5.0/emoji-data.txt
        # which contains the line:
        #
        # “1F9D1..1F9DD  ; Emoji_Modifier_Base  #10.0 [13] (🧑..🧝)    adult..elf”
        >>> matcher.skin_tone_variants('🧘\u200d♀\ufe0f')
        ['\U0001f9d8\u200d♀\ufe0f', '\U0001f9d8🏻\u200d♀\ufe0f', '\U0001f9d8🏼\u200d♀\ufe0f', '\U0001f9d8🏽\u200d♀\ufe0f', '\U0001f9d8🏾\u200d♀\ufe0f', '\U0001f9d8🏿\u200d♀\ufe0f']

        >>> matcher.skin_tone_variants('🏌\ufe0f\u200d♂\ufe0f')
        ['🏌\ufe0f\u200d♂\ufe0f', '🏌🏻\u200d♂\ufe0f', '🏌🏼\u200d♂\ufe0f', '🏌🏽\u200d♂\ufe0f', '🏌🏾\u200d♂\ufe0f', '🏌🏿\u200d♂\ufe0f']

        >>> matcher.skin_tone_variants('✌\ufe0f')
        ['✌\ufe0f', '✌🏻', '✌🏼', '✌🏽', '✌🏾', '✌🏿']

        >>> matcher = EmojiMatcher(languages = ['en'], non_fully_qualified=True)
        >>> matcher.skin_tone_variants('🏌\ufe0f\u200d♂\ufe0f')
        ['🏌\u200d♂', '🏌🏻\u200d♂', '🏌🏼\u200d♂', '🏌🏽\u200d♂', '🏌🏾\u200d♂', '🏌🏿\u200d♂']

        >>> matcher.skin_tone_variants('🏌\u200d♂')
        ['🏌\u200d♂', '🏌🏻\u200d♂', '🏌🏼\u200d♂', '🏌🏽\u200d♂', '🏌🏾\u200d♂', '🏌🏿\u200d♂']
        '''
        if not emoji_string or emoji_string in SKIN_TONE_MODIFIERS:
            return [emoji_string]
        emoji_string = self.variation_selector_16_normalize(
            emoji_string, non_fully_qualified=True)
        if 'Emoji_Modifier_Base' in self.properties(emoji_string):
            return [
                self.variation_selector_16_normalize(
                    emoji_string + tone,
                    non_fully_qualified=self._non_fully_qualified)
                for tone in ('',) + SKIN_TONE_MODIFIERS]
        if ((emoji_string[-1] in SKIN_TONE_MODIFIERS)
            and ((emoji_string, 'en') in self._emoji_dict)):
            return [
                self.variation_selector_16_normalize(
                    emoji_string[:-1] + tone,
                    non_fully_qualified=self._non_fully_qualified)
                for tone in ('',) + SKIN_TONE_MODIFIERS]
        emoji_parts = emoji_string.split('\u200d')
        if len(emoji_parts) >= 2 and len(emoji_parts) <= 4:
            for modifier in SKIN_TONE_MODIFIERS:
                for i, emoji_part in enumerate(emoji_parts):
                    emoji_parts[i] = emoji_part.replace(modifier, '')
            skin_tone_variants = []
            if len(emoji_parts) == 2:
                for variant0 in self.skin_tone_variants(emoji_parts[0]):
                    for variant1 in self.skin_tone_variants(emoji_parts[1]):
                        skin_tone_variants.append(
                            variant0
                            + '\u200d'
                            + variant1)
            if len(emoji_parts) == 3:
                for variant0 in self.skin_tone_variants(emoji_parts[0]):
                    for variant1 in self.skin_tone_variants(emoji_parts[1]):
                        for variant2 in self.skin_tone_variants(emoji_parts[2]):
                            skin_tone_variants.append(
                                variant0
                                + '\u200d'
                                + variant1
                                + '\u200d'
                                + variant2)
            if len(emoji_parts) == 4:
                for variant0 in self.skin_tone_variants(emoji_parts[0]):
                    for variant1 in self.skin_tone_variants(emoji_parts[1]):
                        for variant2 in self.skin_tone_variants(emoji_parts[2]):
                            for variant3 in self.skin_tone_variants(emoji_parts[3]):
                                skin_tone_variants.append(
                                    variant0
                                    + '\u200d'
                                    + variant1
                                    + '\u200d'
                                    + variant2
                                    + '\u200d'
                                    + variant3)
            if skin_tone_variants:
                return skin_tone_variants
        return [self.variation_selector_16_normalize(
            emoji_string,
            non_fully_qualified=self._non_fully_qualified)]


    def debug_loading_data(self):
        '''To debug whether the data has been loaded correctly'''
        count = 0
        for key, value in sorted(self._emoji_dict.items()):
            print("key=%s value=%s" %(key, sorted(value.items())))
            count += 1
        print('count=%s' %count)

    if IMPORT_PINYIN_SUCCESSFUL:
        def _doctest_pinyin(self):
            '''
            >>> matcher = EmojiMatcher(languages = ['zh_CN'])
            >>> matcher.candidates('saima')[0][:2]
            ('🏇', '赛马 “sàimǎ”')

            >>> matcher.similar('🏇', match_limit=3)
            [('🏇', '赛马 [🏇, 赛马, sàimǎ, 马, mǎ]', 5), ('🏇🏻', '赛马: 种类-1-2 [赛马, sàimǎ, 马, mǎ]', 4), ('🏇🏼', '赛马: 种类-3 [赛马, sàimǎ, 马, mǎ]', 4)]

            >>> matcher = EmojiMatcher(languages = ['zh_TW'])

            >>> matcher.candidates('saima')[0][:2]
            ('🏇', '賽馬 “sàimǎ”')

            >>> matcher.similar('🏇', match_limit=1)
            [('🏇', '賽馬 [🏇, 騎馬, qímǎ]', 3)]
            '''

    if IMPORT_PYKAKASI_SUCCESSFUL:
        def _doctest_pykakasi(self):
            '''
            >>> matcher = EmojiMatcher(languages = ['ja_JP'], romaji=True)
            >>> matcher.candidates('katatsumuri')[0][:2]
            ('🐌', 'かたつむり “katatsumuri”')

            >>> matcher.candidates('ねこ＿')[0][:2]
            ('🐈', 'ネコ “ねこ”')

            >>> matcher.similar('🐤', match_limit=5)
            [('🐤', 'ひよこ [🐤, ひな, ひよこ, 動物, どうぶつ, 横を向いているひよこ, よこをむいているひよこ, 顔, かお, 鳥, とり, hina, hiyoko, doubutsu, yokowomuiteiruhiyoko, kao, tori]', 17), ('🐣', '卵からかえったひよこ [ひな, ひよこ, 動物, どうぶつ, 鳥, とり, hina, hiyoko, doubutsu, tori]', 10), ('🐥', '前を向いているひよこ [ひな, ひよこ, 動物, どうぶつ, 鳥, とり, hina, hiyoko, doubutsu, tori]', 10), ('🐦', '鳥 [動物, どうぶつ, 顔, かお, 鳥, とり, doubutsu, kao, tori]', 9), ('🐔', 'にわとり [動物, どうぶつ, 顔, かお, 鳥, とり, doubutsu, kao, tori]', 9)]

            >>> matcher.similar('🐌', match_limit=5)
            [('🐌', 'かたつむり [🐌, かたつむり, でんでん虫, でんでんむし, 虫, むし, katatsumuri, dendenmushi, mushi]', 9), ('🦋', 'チョウ [虫, むし, mushi]', 3), ('🐛', '毛虫 [虫, むし, mushi]', 3), ('🐜', 'アリ [虫, むし, mushi]', 3), ('🐝', 'ミツバチ [虫, むし, mushi]', 3)]

            >>> matcher.similar('😱', match_limit=5)
            [('😱', '恐怖 [😱, がーん, ショック, しょっく, 叫び, さけび, 恐怖, きょうふ, 顔, かお, ga-n, shokku, sakebi, kyoufu, kao]', 15), ('🙀', '絶望する猫 [がーん, ショック, しょっく, 顔, かお, ga-n, shokku, kao]', 8), ('🤯', '頭爆発 [ショック, しょっく, 顔, かお, shokku, kao]', 6), ('😨', '青ざめ [がーん, 顔, かお, ga-n, kao]', 5), ('😰', '冷や汗青ざめ [顔, かお, kao]', 3)]

            '''

    def list_emoji_one_bugs(self):
        '''
        '''
        print('--------------------------------------------------')
        print('Possible bugs in emojione.json:')
        print('--------------------------------------------------')
        print('\n')
        for emoji_key, emoji_value in sorted(self._emoji_dict.items()):
            if emoji_key[1] == 'en':
                if ((emoji_key[0] + SKIN_TONE_MODIFIERS[0], 'en')
                    in self._emoji_dict):
                    if (not 'Emoji_Modifier_Base'
                        in self.properties(emoji_key[0])):
                        print('emoji “%s” (U+%X) has skintones in emojione '
                              %(emoji_key[0], ord(emoji_key[0]))
                              + 'but not the Emoji_Modifier_Base '
                              + 'property in emoji-data.txt.')
                if 'Emoji_Modifier_Base' in self.properties(emoji_key[0]):
                    if (not 'emoji_order'
                        in self._emoji_dict[
                            (emoji_key[0] + SKIN_TONE_MODIFIERS[0], 'en')]):
                        print('emoji “%s” (U+%X) '
                              %(emoji_key[0], ord(emoji_key[0]))
                              + 'has the property Emoji_Modifier_Base '
                              + 'in emoji-data.txt but no skin tones '
                              + 'in emojione.')
                if 'Emoji_ZWJ_Sequence' in self.properties(emoji_key[0]):
                    if ('emoji_order'
                        not in self._emoji_dict[(emoji_key[0], 'en')]):
                        print('ZWJ sequence “%s” '
                              %emoji_key[0]
                              + 'from unicode.org missing in emojione')
                else:
                    if (('emoji_order'
                        in self._emoji_dict[(emoji_key[0], 'en')])
                        and '\u200d' in emoji_key[0]):
                        print('ZWJ sequence “%s” '
                              %emoji_key[0]
                              + 'in emojione but not in unicode.org')

BENCHMARK = True

def main():
    '''
    Used for testing and profiling.

    “python3 itb_emoji.py”

    runs some tests and prints profiling data.
    '''
    if BENCHMARK:
        import cProfile
        import pstats
        profile = cProfile.Profile()
        profile.enable()

    failed = False
    if False:
        matcher = EmojiMatcher(
            languages=['en_US', 'it_IT', 'es_MX', 'es_ES', 'de_DE',
                       'ja_JP', 'zh_TW', 'zh_CN'],
            unicode_data=True, cldr_data=True)
        matcher.debug_loading_data()
        matcher.list_emoji_one_bugs()
    else:
        import doctest
        # Set the domain name to something invalid to avoid using
        # the translations for the doctest tests. Translations may
        # make the tests fail just because some translations are
        # added, changed, or missing.
        global DOMAINNAME
        DOMAINNAME = ''
        (failed, dummy_attempted) = doctest.testmod()

    if BENCHMARK:
        profile.disable()
        stats = pstats.Stats(profile)
        stats.strip_dirs()
        stats.sort_stats('cumulative')
        stats.print_stats('itb_emoji', 25)
        stats.print_stats('difflib', 25)
        stats.print_stats('enchant', 25)

    if failed:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
