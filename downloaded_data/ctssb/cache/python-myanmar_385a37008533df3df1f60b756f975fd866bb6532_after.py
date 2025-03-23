# converter.py - converter module
# coding: utf-8
# The MIT License (MIT)
# Copyright (c) 2018 Thura Hlaing

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
# OR OTHER DEALINGS IN THE SOFTWARE.

import sys
import itertools

from myanmar import language
from myanmar import encodings


def get_supported_encodings():
    """
    Get a list of encodings supported by ``converter`` module.

    >>> get_supported_encodings()
    ['unicode', 'zawgyi']
    """
    return ['unicode', 'zawgyi']


encoders = {
    "unicode": encodings.UnicodeEncoding(),
    "zawgyi": encodings.ZawgyiEncoding(),
}


def convert(text, fromenc, toenc):
    """
    Convert text in ``fromenc`` encoding to ``toenc`` encoding.

    >>> convert('အကျိုးတရား', 'unicode', 'zawgyi')
    'အက်ိဳးတရား'
    >>> convert('ဉာဏ္ႀကီးရွင္', 'zawgyi', 'unicode')
    'ဉာဏ်ကြီးရှင်'
    """
    if fromenc not in encoders:
        raise NotImplementedError("Unsupported encoding: %s" % fromenc)

    if toenc not in encoders:
        raise NotImplementedError("Unsupported encoding: %s" % toenc)

    from_encoder = encoders[fromenc]
    to_encoder = encoders[toenc]
    iterator = language.SyllableIter(text=text, encoding=from_encoder)
    # print (from_encoder.get_pattern())

    otext = ""
    for each_syllable in iterator:
        complete_syllable = each_syllable['syllable']
        if len(each_syllable) == 1:
            # unmatched text, no need to convert
            otext += complete_syllable
            continue

        if complete_syllable in from_encoder.reverse_table:
            # Direct mapping
            key = from_encoder.reverse_table[complete_syllable]
            key = key[:key.find('_')
                      ] if '_' in key else key  # remove variant suffixes
            otext += to_encoder.table[key]
            continue

        # flattern syllable_pattern, convert to a list of tuples first
        syllable_pattern = [
            (x, ) if isinstance(x, str) else x
            for x in to_encoder.syllable_pattern
        ]
        syllable_pattern = list(itertools.chain(*syllable_pattern))

        # collect codepoints in syllable, in correct syllable order
        syllable = {}
        flags = {}

        for each_part in each_syllable.keys():
            if each_part == 'syllable':
                continue  # skip complete syllable

            key = from_encoder.reverse_table[each_syllable[each_part]]
            key = key[:key.find('_')
                      ] if '_' in key else key  # remove variant suffixes

            if each_part == "consonant":
                if key == "na":
                    key += choose_na_variant(each_syllable)

                if key == "ra":
                    key += choose_ra_variant(each_syllable)

                if key == "nnya":
                    key += choose_nnya_variant(each_syllable)

            if each_part == "yapin":
                key += choose_yapin_variant(each_syllable)

            if each_part == "yayit":
                key += choose_yayit_variant(each_syllable)

            if each_part == "uVowel":
                key += choose_uvowel_variant(each_syllable)
                flags[each_part] = key

            if each_part == "aaVowel":
                key += choose_aavowel_variant(each_syllable)

            if each_part == "dotBelow":
                key += choose_dot_below_variant(each_syllable)
            syllable[each_part] = key

        # print(each_syllable, "---", syllable)
        if 'uVowel' in syllable and 'hatoh' in syllable:
            del syllable['uVowel']
            syllable['hatoh'] = syllable['hatoh'] + '_' + flags['uVowel']

        if 'wasway' in syllable and 'hatoh' in syllable:
            del syllable['hatoh']
            syllable['wasway'] = syllable['wasway'] + '-' + 'hatoh'

        for each_pattern in syllable_pattern:
            if each_pattern not in syllable:
                continue

            try:
                key = syllable[each_pattern]
                otext += to_encoder.table[key]
            except Exception as e:
                print(key, syllable)

    # pprint (to_encoder.table)
    # pprint (from_encoder.reverse_table)
    return otext


def is_wide_consonant(char):
    WIDE_CONSONANTS = [
        language.LETTER_KA, language.LETTER_GHA, language.LETTER_CA,
        language.LETTER_CHA, language.LETTER_NYA, language.LETTER_NNA,
        language.LETTER_TA, language.LETTER_THA, language.LETTER_BHA,
        language.LETTER_YA, language.LETTER_LA, language.LETTER_SA,
        language.LETTER_HA, language.LETTER_A, language.LETTER_GREAT_SA
    ]
    return char in WIDE_CONSONANTS


def is_lower_consonant(char):
    LOWER_CONSONANTS = [
        language.LETTER_NYA,
        # ... more
        language.LETTER_NA,
        language.LETTER_RA,
    ]
    return char in LOWER_CONSONANTS


def has_lower_marks(syllable, filters=[]):
    MAKRS = ["stack", "wasway", "yapin", "yayit", "hatoh", "uVowel"]
    for mark in [m for m in MAKRS if m not in filters]:
        if mark in syllable:
            return True
    return False


def has_upper_marks(syllable, filters=[]):
    MAKRS = ["kinzi", "yapin", "iVowel", "aiVowel", "anusvara"]
    for mark in [m for m in MAKRS if m not in filters]:
        if mark in syllable:
            return True
    return False


def choose_ra_variant(syllable):
    key = "_alt" if has_lower_marks(syllable, ["hatoh"]) else ""
    return key


def choose_na_variant(syllable):
    key = "_alt" if has_lower_marks(syllable) else ""
    return key


def choose_nnya_variant(syllable):
    key = "_alt" if has_lower_marks(syllable) else ""
    return key


def choose_uvowel_variant(syllable):
    key = "_tall" if has_lower_marks(syllable, ["uVowel", "hatoh"]) else ""
    return key


def choose_aavowel_variant(syllable):
    _C = [
        language.LETTER_KHA, language.LETTER_GHA, language.LETTER_NGA,
        language.LETTER_DA, language.LETTER_DHA, language.LETTER_PA,
        language.LETTER_WA
    ]

    # FIXME: asat
    key = ''
    # if 'asat' in syllable:
    #     key += '-asat'

    if syllable['consonant'] in _C:
        for c in ['yapin', 'yayit', 'wasway', 'hatoh']:
            if c in syllable:
                break
        else:
            key += '_tall'

    return key


def choose_yayit_variant(syllable):
    key = "_wide" if is_wide_consonant(syllable['consonant']) else "_narrow"
    key += "_lower" if has_lower_marks(syllable, ["yayit", "uVowel"]) else ""
    key += "_upper" if has_upper_marks(syllable, ["yayit"]) else ""
    return key


def choose_yapin_variant(syllable):
    key = "_alt" if has_lower_marks(syllable, ["yapin", "uVowel"]) else ""
    return key


def choose_dot_below_variant(syllable):
    key = ""

    if syllable['consonant'] == language.LETTER_NA:
        key += "_alt"
    elif syllable['consonant'] == language.LETTER_RA:
        key += "_alt_alt"
    elif "uVowel" in syllable:
        key += "_alt_alt" if 'yayit' in syllable else '_alt'
    elif "yapin" in syllable:
        key += "_alt"
    elif "wasway" in syllable:
        key += "_alt_alt"

    return key


def main():
    import argparse
    import fileinput

    parser = argparse.ArgumentParser(
        description='Convert between various Myanmar encodings'
    )
    parser.add_argument(
        '-f',
        '--from',
        dest='fro',
        action='store',
        required=True,
        help='convert characters from ENCODING',
        metavar="ENCODING",
    )
    parser.add_argument(
        '-t',
        '--to',
        dest='to',
        action='store',
        required=True,
        help='convert characters to ENCODING',
        metavar="ENCODING",
    )
    parser.add_argument(
        'files',
        metavar='FILE',
        nargs='*',
        help='files to convert, if empty, stdin is used'
    )

    args = parser.parse_args()
    if args.fro not in get_supported_encodings():
        print(
            "%s is not a supported encoding. Should be any of %s." %
            (args.fro, get_supported_encodings())
        )
        sys.exit(-1)

    if args.to not in get_supported_encodings():
        print(
            "%s is not a supported encoding. Should be any of %s." %
            (args.to, get_supported_encodings())
        )
        sys.exit(-1)

    if args.fro == args.to:
        print("from encoding must not be the same as to encoding.")
        sys.exit(-1)

    for line in fileinput.input(files=args.files):
        print(convert(line, args.fro, args.to), end='')


if __name__ == "__main__":
    main()
