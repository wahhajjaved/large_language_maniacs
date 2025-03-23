# -*- encoding: utf-8 -*-

import json
import os
import logging

from MoinMoin.Page import Page
from MoinMoin import caching, wikiutil

def _json_key(page_name, parser_name, rev):
    # This is a bit vulnerable, but I believe it's not a big problem...
    return (u'%s#%s#%d' % (page_name, parser_name, rev)).encode('utf-8')

def load_json_text_from_page(request, parser, page_name, parser_name):
    formatterClass = wikiutil.searchAndImportPlugin(
        request.cfg, 'formatter', 'extracting_formatter')
    extracting_formatter = formatterClass(parser_name, request)
    # Request rev (number) is only available for the requested page.
    rev = request.rev or 0 if request.page.page_name == page_name else 0
    page = Page(request, page_name, formatter=extracting_formatter, rev=rev)

    # this is so we get a correctly updated data if we just preview in the editor -
    # the new content is not stored on disk yet, but available as macro.parser.raw:
    if parser:
        format = '#format %s\n' % page.pi['format']
        page.set_raw_body(format + parser.raw, modified=1)

    if not page.isStandardPage(includeDeleted=False):
        return None
    extracting_formatter.setPage(page)
    
    # Discarding the return value
    request.redirectedOutput(
        Page.send_page_content, page, request, page.data, 'wiki')

    return extracting_formatter.get_extracted()

def _load_all_jsons(request):
    character_names = load_json_from_page(
        request, None, u'CharacterList', u'characters') or {}
    wp_names = set()
    weapon_names = set()
    weapon_name_queue = []

    characters = []
    wps = []
    weapons = []

    if not character_names or not isinstance(character_names, list):
        return None

    for c_name in character_names:
        # make sure to be an unicode object
        c_name = unicode(c_name) if c_name else u'BadCharacterName'
        c = load_json_from_page(request, None, c_name, u'character') or {}
        characters.append(c)
        wp_names.update(c.get(u'ウェポンパック', []) or [])

    for wp_name in wp_names:
        wp_name = unicode(wp_name) if wp_name else u'BadWPName'
        wp = load_json_from_page(request, None, wp_name, u'wp') or {}
        wps.append(wp)
        for equip_name in [u'右手武器', u'左手武器',
                           u'サイド武器', u'タンデム武器']:
            weapon_name = wp.get(equip_name, {}).get(u'名称', u'')
            weapon_names.add(weapon_name)

    weapon_name_queue = list(weapon_names)
    while weapon_name_queue:
        w_name = weapon_name_queue.pop()
        w_name = unicode(w_name) if w_name else u'BadWeaponName'
        weapon = load_json_from_page(request, None, w_name, u'weapon') or {}

        for leveled_weapon in weapon.get(u'レベル', {}).itervalues():
            if u'サブウェポン' in leveled_weapon:
                subweapon_name = leveled_weapon.get(u'サブウェポン', {}).get(u'名称', u'')
                if subweapon_name and subweapon_name not in weapon_names:
                    weapon_names.add(subweapon_name)
                    weapon_name_queue.append(subweapon_name)
        weapons.append(weapon)

    return {u'characters': characters, u'wps': wps, u'weapons': weapons}

def load_json_from_page(request, parser, page_name, parser_name):
    """
    IMPORTANT: give parser only if you are sure that the parser is for the requested page_name.
    Otherwise, give None.
    """

    # Request rev (number) is only available for the requested page.
    rev = request.rev or 0 if request.page.page_name == page_name else 0

    has_parser = True if parser else False
    use_cache = not has_parser
    cache = caching.CacheEntry(
        request, 'gswiki-pagejson', _json_key(page_name, parser_name, rev),
        'wiki', use_pickle=True)
    if (not use_cache or
        cache.needsUpdate(Page(request, page_name)._text_filename().encode('utf-8'))):
        json_text = load_json_text_from_page(request, parser, page_name, parser_name)
        j = u''
        if json_text:
            try:
                j = json.loads(json_text)
            except Exception as e:
                logging.warning(u'Something is wrong: %s', e)
                pass
        if use_cache:
            cache.update(j)
    else:
        j = cache.content()

    return j or None

def load_all_jsons(request):
    cache = caching.CacheEntry(
        request, 'gswiki-alljsons', 'json', 'wiki',
        use_pickle=True)
    if cache.needsUpdate(os.path.join(request.cfg.data_dir, 'edit-log')):
        j = _load_all_jsons(request)
        cache.update(j)
    else:
        j = cache.content()

    return j
