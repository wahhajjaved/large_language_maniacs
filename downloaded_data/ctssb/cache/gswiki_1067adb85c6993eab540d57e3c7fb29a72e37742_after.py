# -*- encoding: utf-8 -*-

import json
import os

from MoinMoin.Page import Page
from MoinMoin import caching, wikiutil

def _json_key(page_name, parser_name):
    # This is a bit vulnerable, but I believe it's not a big problem...
    return (u'%s#%s' % (page_name, parser_name)).encode('utf-8')

def load_json_text_from_page(request, page_name, parser_name):
    formatterClass = wikiutil.searchAndImportPlugin(
        request.cfg, 'formatter', 'extracting_formatter')
    extracting_formatter = formatterClass(parser_name, request)
    page = Page(request, page_name, formatter=extracting_formatter)
    if not page.isStandardPage(includeDeleted=False):
        return None
    extracting_formatter.setPage(page)
    
    # Discarding the return value
    request.redirectedOutput(
        Page.send_page_content, page, request, page.data, 'wiki')

    return extracting_formatter.get_extracted()

def _load_all_jsons(request):
    character_names = load_json_from_page(request, u'CharacterList', u'characters') or {}
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
        c = load_json_from_page(request, c_name, u'character') or {}
        characters.append(c)
        wp_names.update(c.get(u'ウェポンパック', []) or [])

    for wp_name in wp_names:
        wp_name = unicode(wp_name) if wp_name else u'BadWPName'
        wp = load_json_from_page(request, wp_name, u'wp') or {}
        wps.append(wp)
        for equip_name in [u'右手武器', u'左手武器',
                           u'サイド武器', u'タンデム武器']:
            weapon_name = wp.get(equip_name, {}).get(u'名称', u'')
            weapon_names.add(weapon_name)

    weapon_name_queue = list(weapon_names)
    while weapon_name_queue:
        w_name = weapon_name_queue.pop()
        w_name = unicode(w_name) if w_name else u'BadWeaponName'
        weapon = load_json_from_page(request, w_name, u'weapon') or {}

        for leveled_weapon in weapon.get(u'レベル', {}).itervalues():
            if u'_サブウェポン' in leveled_weapon:
                subweapon_name = leveled_weapon.get(u'サブウェポン', {}).get(u'名称', u'')
                if subweapon_name and subweapon_name not in weapon_names:
                    weapon_names.add(subweapon_name)
                    weapon_name_queue.push(subweapon_name)
        weapons.append(weapon)

    return {u'characters': characters, u'wps': wps, u'weapons': weapons}

def load_json_from_page(request, page_name, parser_name):
    cache = caching.CacheEntry(
        request, 'gswiki-pagejson', _json_key(page_name, parser_name), 'wiki',
        use_pickle=True)
    if cache.needsUpdate(Page(request, page_name)._text_filename().encode('utf-8')):
        json_text = load_json_text_from_page(request, page_name, parser_name)
        j = u''
        if json_text:
            try:
                j = json.loads(json_text)
            except Error:
                pass
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
