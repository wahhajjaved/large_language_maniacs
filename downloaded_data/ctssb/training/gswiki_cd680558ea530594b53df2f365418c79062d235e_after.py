
# -*- coding: utf-8 -*-

from utils.table import Table, Row, Cell
from utils.json_loader import load_json_from_page

from MoinMoin.macro import Include

Dependencies = ['pages']

generates_headings = True

def macro_CharacterWPs(macro, prefix=u'', character_name=None):
    request = macro.request
    formatter = macro.formatter
    parser = macro.parser

    if not character_name:
        pagename = macro.formatter.page.page_name
        if pagename.startswith(prefix):
            pagename = pagename[len(prefix):]
        character_name = pagename
    else:
        parser = None

    return create_wp_list(macro, request, parser, formatter, prefix, character_name)

def create_wp_list(macro, request, parser, formatter, prefix, character_name):
    j = load_json_from_page(request, parser, prefix + character_name, u'character')
    if not j:
        return 'No WP(s) are defined for this character.'

    j = j.get(u'ウェポンパック', [])
    text = u''
    last_parser = macro.parser
    for wp_name in j:
        include_args = u'%(prefix)s%(wp_name)s, "%(wp_name)s", 3, from="=== %(wp_name)s ===", to="==== コメント ===="' % {
            u'wp_name': wp_name,
            u'prefix': prefix }
        text += Include.execute(macro, include_args)
    return text
