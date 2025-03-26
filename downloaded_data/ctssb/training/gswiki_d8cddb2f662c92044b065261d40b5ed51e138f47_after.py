# -*- coding: utf-8 -*-

from utils.table import Table, Row, Cell
from utils.json_loader import load_json_from_page, load_all_jsons

import math

Dependencies = ['pages']

def macro_WeaponData(macro, prefix=u'', _trailing_args=[]):
    request = macro.request
    formatter = macro.formatter
    parser = macro.parser

    requested_weapons = _trailing_args
    if not requested_weapons:
        # assume the caller requested to show a weapon data of the current page.
        pagename = macro.formatter.page.page_name
        if pagename.startswith(prefix):
            pagename = pagename[len(prefix):]
        requested_weapons = [pagename]
    else:
        parser = None

    if len(requested_weapons) == 1:
        pass
    else:
        raise NotImplementedError()

    return create_weapon_data(request, parser, formatter, prefix, requested_weapons,
                              show_wp_owners=True)

def get_weapon_owner_wps(request, prefix, weapon, level):
    j = load_all_jsons(request, prefix) or {}
    # The weapon may be owned as a subtrigger of other weapons.
    # List up all weapons has the weapon as subtrigger (or as main trigger)
    weapons = set()
    weapons.add((weapon, level))
    for w in j.get(u'weapons', []):
        for l, leveled_weapon in w.get(u'レベル', {}).iteritems():
            l = int(l)
            subw = leveled_weapon.get(u'サブウェポン', None)
            if not subw:
                continue
            if subw.get(u'名称', u'') == weapon and subw.get(u'レベル', -1) == level:
                weapons.add((w.get(u'名称', u''), l))

    wps = []
    for wp in j.get(u'wps', []):
        for equip_name in [u'右手武器', u'左手武器',
                           u'サイド武器', u'タンデム武器']:
            w = wp.get(equip_name, {})
            item = (w.get(u'名称', u''), w.get(u'レベル', -1))
            if item in weapons:
                wps.append(wp.get(u'名称', u'BadWPName'))
                break

    return wps

def create_weapon_data(request, parser, formatter, prefix, requested_weapons, **kw):
    assert(len(requested_weapons) == 1)
    j = load_json_from_page(request, parser, prefix + requested_weapons[0], u'weapon') or {}
    if not j:
        return u'No weapon data'
    table = Table()
    create_table(request, prefix, j, table, formatter, **kw)
    html_table = table.toHtmlTable()
    return (formatter.linebreak(preformatted=False)
            + formatter.text(u'弾種: %s' % j[u'弾種'])
            + html_table.format(formatter))

def create_table(request, prefix, j, table, formatter, **kw):
    levels = list(j.get(u'レベル', {}).iteritems())
    levels.sort()
    for (level, weapon) in levels:
        level = int(level)
        row = Row()
        create_row(request, prefix, j, row, level, formatter,
            subtrigger_in_row=True, subweapon_in_row=True, **kw)
        table.rows.append(row)

def create_row(request, prefix, j, row, level, formatter, **kw):
    """
    @keyword subtrigger_in_row True to put subtrigger effect into 備考
    @keyword subweapon_in_row True to put subweapon name into 備考
    @keyword show_name True to add weapon name at the top of the row
    @keyword show_wp_owners True to show wp owners list
    @keyword is_xi_side True to add Xi vulkan
    @keyword is_xi_tandem True to add Xi grenade
    """
    weapon = j.get(u'レベル', {}).get(u'%d' % level)
    if not weapon:
        return
    key_trimmed_weapon = []
    for key, value in weapon.iteritems():
        if isinstance(key, unicode):
            key = key.lstrip(u'_')
        key_trimmed_weapon.append((key, value))
    weapon = dict(key_trimmed_weapon)

    if kw.get('show_name', False):
        name = j.get(u'名称', u'')
        row.cells.append(Cell(
            u'武装名',
            formatter.pagelink(True, prefix + name) + formatter.text(name) + formatter.pagelink(False),
            cls=[u'center', u'hc'],
            formatted=True
        ))

    row.cells.append(Cell(u'ﾚﾍﾞﾙ', u'Lv.%d' % level, cls=[u'right']))

    if u'攻撃力' in weapon:
        power = u'%d' % weapon[u'攻撃力']
        if u'分裂数' in weapon:
            power += u'x%d' % weapon[u'分裂数']
        if u'覚醒攻撃力' in weapon:
            power += u'(%d)' % weapon[u'覚醒攻撃力']
        row.cells.append(Cell(u'攻撃力', power, cls=[u'right']))
    elif u'散弾攻撃力' in weapon:
        power = u'%dx%s' % (weapon[u'散弾攻撃力'], weapon.get(u'分裂数', u'?'))
        row.cells.append(Cell(u'攻撃力', power, cls=[u'right']))
    elif u'攻撃力(爆風)' in weapon:
        power = u'%d' % weapon[u'攻撃力(爆風)']
        if u'分裂数' in weapon:
            power += u'x%d' % weapon[u'分裂数']
        # We don't need "(爆風)" annotation in display, isn't it?
        row.cells.append(Cell(u'攻撃力', power, cls=[u'right']))
    elif u'回復力' in weapon:
        power = u'%d' % weapon[u'回復力']
        if u'分裂数' in weapon:
            power += u'x%d' % weapon[u'分裂数']
        row.cells.append(Cell(u'回復力', u'%s' % power, cls=[u'right']))
    elif u'防御力' in weapon:
        row.cells.append(Cell(u'防御力', u'%d' % weapon[u'防御力'], cls=[u'right']))
    elif u'吸引力' in weapon:
        row.cells.append(Cell(u'吸引力', u'%d' % weapon[u'吸引力'], cls=[u'right']))
    elif u'弾薬補給割合' in weapon:
        row.cells.append(Cell(u'補給', u'%d%%' % weapon[u'弾薬補給割合'], cls=[u'right']))
    else:
        row.cells.append(None)

    if ((u'コンボ蓄積値' in weapon and u'灰ダウン蓄積値' in weapon)
        and (u'攻撃力' in weapon or u'散弾攻撃力' in weapon or u'攻撃力(爆風)' in weapon)):
        base = weapon.get(u'攻撃力', 0) or weapon.get(u'散弾攻撃力', 0) or weapon.get(u'攻撃力(爆風)', 0)
        total = get_total_damage_str(
            base, float(weapon.get(u'コンボ蓄積値', u'0.0')),
            float(weapon.get(u'灰ダウン蓄積値', 0)))
        if u'覚醒攻撃力' in weapon:
            total2 = get_total_damage_str(float(weapon.get(u'覚醒攻撃力', 0)),
                                          float(weapon.get(u'コンボ蓄積値', u'0.0')),
                                          float(weapon.get(u'灰ダウン蓄積値', 0)))
            total += u'(%s)' % total2
        row.cells.append(Cell(u'総ダメージ', total, cls=[u'right']))
    else:
        row.cells.append(None)

    # Very special case: both 防御力 and 回復力 are existing. (回復エリアシールド).
    # Add another column in this case.
    if u'防御力' in weapon and u'回復力' in weapon:
        row.cells.append(Cell(u'防御力', u'%d' % weapon[u'防御力'], cls=[u'right']))
    else:
        row.cells.append(None)

    if u'反動ダメージ量' in weapon:
        row.cells.append(Cell(u'反動', u'%d' % weapon[u'反動ダメージ量'], cls=[u'right']))
    elif u'反動ダメージ割合' in weapon:
        row.cells.append(Cell(u'反動', u'%d%%' % weapon[u'反動ダメージ割合'], cls=[u'right']))
    else:
        row.cells.append(None)

    if u'連射間隔' in weapon:
        row.cells.append(Cell(u'連射間隔', u'%dF' % weapon[u'連射間隔'], cls=[u'right']))
    else:
        row.cells.append(None)

    if u'ロックオン時間' in weapon:
        row.cells.append(Cell(u'ﾛｯｸｵﾝ時間', u'%dF' % weapon[u'ロックオン時間'], cls=[u'right']))
    elif u'チャージ時間' in weapon:
        row.cells.append(Cell(u'ﾁｬｰｼﾞ時間', u'%dF' % weapon[u'チャージ時間'], cls=[u'right']))
    elif u'点火時間' in weapon:
        row.cells.append(Cell(u'点火時間', u'%dF' % weapon[u'点火時間'], cls=[u'right']))
    elif u'発射準備時間' in weapon:
        row.cells.append(Cell(u'発射準備時間', u'%dF' % weapon[u'発射準備時間'], cls=[u'right']))
    else:
        row.cells.append(None)

    if u'シールド展開時間' in weapon:
        row.cells.append(Cell(u'展開時間', u'%dF' % weapon[u'シールド展開時間'], cls=[u'right']))
    elif u'最低持続時間' in weapon:
        row.cells.append(Cell(u'最低持続', u'%dF' % weapon[u'最低持続時間'], cls=[u'right']))
    elif u'移動時間' in weapon:
        row.cells.append(Cell(u'移動時間', u'%dF' % weapon[u'移動時間'], cls=[u'right']))
    elif u'効果時間' in weapon:
        row.cells.append(Cell(u'効果時間', u'%dF' % weapon[u'効果時間'], cls=[u'right']))
    else:
        row.cells.append(None)

    if u'装填数' in weapon:
        row.cells.append(Cell(u'装填数', u'%d' % weapon[u'装填数'], cls=[u'right']))
    else:
        row.cells.append(None)

    if u'リロード分子' in weapon and u'リロード分母' in weapon:
        numerator = weapon[u'リロード分子']
        numerator = u'全弾' if numerator == u'all' else u'%d' % numerator
        row.cells.append(Cell(u'ﾘﾛｰﾄﾞ',
                    u'%s/%dF' % (numerator, weapon[u'リロード分母']),
                    cls=[u'right']))
    else:
        row.cells.append(None)

    ### I think this column was not much useful, and it's title was space wasting,
    ### so commenting out it for now.
    # if u'リロード分子' in weapon and u'リロード分母' in weapon and u'装填数' in weapon:
    #     if weapon[u'リロード分子'] == u'all':
    #         row.cells.append(Cell(u'ﾘﾛｰﾄﾞ時間',
    #                     u'%dF' % weapon[u'リロード分母'],
    #                     cls=[u'right']))
    #     else:
    #         reload_num = int(math.ceil(
    #                 float(weapon[u'装填数']) 
    #                 / float(weapon[u'リロード分子'])))
    #         row.cells.append(Cell(u'ﾘﾛｰﾄﾞ時間', 
    #                     u'%dF' % (reload_num * int(weapon[u'リロード分母'])),
    #                     cls=[u'right']))
    # else:
    #     row.cells.append(None)

    if u'射程距離' in weapon:
        row.cells.append(Cell(u'射程', u'%dm' % weapon[u'射程距離'], cls=[u'right']))
    elif u'散弾射程' in weapon:
        row.cells.append(Cell(u'射程', u'%dm' % weapon[u'散弾射程'], cls=[u'right']))
    else:
        row.cells.append(None)

    if u'攻撃範囲' in weapon:
        row.cells.append(Cell(u'攻撃範囲', u'%.1fm' % weapon[u'攻撃範囲'], cls=[u'right']))
    elif u'シールド範囲' in weapon:
        row.cells.append(Cell(u'ｼｰﾙﾄﾞ範囲', u'%dm' % weapon[u'シールド範囲'], cls=[u'right']))
    elif u'効果範囲' in weapon:
        row.cells.append(Cell(u'効果範囲', u'%dm' % weapon[u'効果範囲'], cls=[u'right']))
    elif u'回復範囲' in weapon:
        row.cells.append(Cell(u'回復範囲', u'%dm' % weapon[u'回復範囲'], cls=[u'right']))
    elif u'弾薬回復範囲' in weapon:
        row.cells.append(Cell(u'補給範囲', u'%dm' % weapon[u'弾薬回復範囲'], cls=[u'right']))
    elif u'爆発範囲' in weapon:
        row.cells.append(Cell(u'爆発範囲', u'%dm' % weapon[u'爆発範囲'], cls=[u'right']))
    else:
        row.cells.append(None)

    notes = []
    has_subtrigger = False
    if u'備考' in weapon:
        notes.append(formatter.text(weapon[u'備考']))
    if kw.get('subweapon_in_row', False) and u'サブウェポン' in weapon:
        has_subtrigger = True
        subweapon = weapon[u'サブウェポン']
        note = (formatter.text(u'サブ: ')
                + formatter.pagelink(True, prefix + subweapon[u'名称'])
                + formatter.text(u'%s Lv.%d' % (subweapon[u'名称'], subweapon[u'レベル']))
                + formatter.pagelink(False))
        notes.append(note)
    if kw.get('subtrigger_in_row', True) and u'サブトリガー' in weapon:
        has_subtrigger = True
        notes.append(formatter.text(u'サブ: %s' % weapon[u'サブトリガー']))
    if kw.get('subweapon_in_row', False) and kw.get('is_xi_side', False) and not has_subtrigger:
        note = (formatter.text(u'サブ: ')
                + formatter.pagelink(True, prefix + u'クシーバルカン')
                + formatter.text(u'%s Lv.%d' % (u'クシーバルカン', 1))
                + formatter.pagelink(False))
        notes.append(note)
    if kw.get('subweapon_in_row', False) and kw.get('is_xi_tandem', False) and not has_subtrigger:
        note = (formatter.text(u'サブ: ')
                + formatter.pagelink(True, prefix + u'クシーグレネード')
                + formatter.text(u'%s Lv.%d' % (u'クシーグレネード', 1))
                + formatter.pagelink(False))
        notes.append(note)
    if notes:
        notes_text = formatter.linebreak(preformatted=False).join(notes)
        row.cells.append(Cell(u'備考', notes_text, cls=[u'center'], formatted=True))
    else:
        row.cells.append(None)

    if kw.get('show_wp_owners', False):
        owner_names = get_weapon_owner_wps(request, prefix, j.get(u'名称', u''), level)
        lines = []
        for owner in owner_names:
            line = u''
            line += formatter.pagelink(True, prefix + owner)
            line += formatter.text(owner) 
            line += formatter.pagelink(False)
            lines.append(line)
        owners_text = formatter.linebreak(preformatted=False).join(lines)
        row.cells.append(Cell(u'所有WP', owners_text, cls=[u'center'], formatted=True))

COMBO_ACCUMULATION_TABLE = [
    max(1.0/7, pow(x/50.0 - 1, 2)) for x in range(34)
]
def get_total_damage_str(base, combo_accum, down_accum):
    # for now, since we don't know robots' down resistance,
    # we only calculate for human's total damage.
    hit = int(math.ceil(100.0 / down_accum))
    total = 0
    for i in range(hit):
        accum_i = min(math.floor(combo_accum * i), len(COMBO_ACCUMULATION_TABLE)-1)
        accum_i = int(math.floor(accum_i))
        total += base * COMBO_ACCUMULATION_TABLE[accum_i]
    return u'%d' % math.floor(total)
