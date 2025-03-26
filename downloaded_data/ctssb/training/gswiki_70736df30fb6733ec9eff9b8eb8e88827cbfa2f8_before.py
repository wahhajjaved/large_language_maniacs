# -*- coding: utf-8 -*-

from utils.table import Table, Row, Cell, TitleRow, TitleCell
from utils.json_loader import load_json_from_page
import WeaponData

Dependencies = ['pages']

def macro_CharacterDataList(macro, _trailing_args=[]):    
    request = macro.request
    formatter = macro.formatter

    return create_character_data_list(request, formatter)

def create_character_data_list(request, formatter):
    table = Table()
    
    characters = load_json_from_page(request, parser, u'CharacterList', u'characters') or []
    header_row = TitleRow()
    newline = formatter.linebreak(preformatted=False)
    header_row.cells.append(TitleCell(u'キャラクター', formatted=True, cls=['center']))
    header_row.cells.append(TitleCell(u'よろけにくさ', formatted=True, cls=['center']))
    header_row.cells.append(TitleCell(u'ジャンプ%s上昇力' % newline, formatted=True, cls=['center']))
    header_row.cells.append(TitleCell(u'空中ダッシュ%s初速度' % newline, formatted=True, cls=['center']))
    header_row.cells.append(TitleCell(u'空中ダッシュ%s最終速度' % newline, formatted=True, cls=['center']))
    header_row.cells.append(TitleCell(u'腕力', formatted=True, cls=['center']))
    header_row.cells.append(TitleCell(u'格闘距離', formatted=True, cls=['center']))
    table.rows.append(header_row)

    for character_name in characters:
        c = load_json_from_page(request, None, character_name, u'character') or {}
        data = c.get(u'キャラクターデータ', {})
        row = Row()
        row.cells.append(Cell(None, character_name, cls=['center']))
        row.cells.append(Cell(None, data.get(u'よろけにくさ', u''), cls=['center']))
        row.cells.append(Cell(None, data.get(u'ジャンプ上昇力', u''), cls=['center']))
        row.cells.append(Cell(None, data.get(u'空中ダッシュ初速度', u''), cls=['center']))
        row.cells.append(Cell(None, data.get( u'空中ダッシュ最終速度', u''), cls=['center']))
        row.cells.append(Cell(None, data.get( u'腕力', u''), cls=['center']))
        row.cells.append(Cell(None, u'%dm' % data.get(u'格闘距離', 0), cls=['right']))
        table.rows.append(row)
    
    html_table = table.toHtmlTable(generate_header=False)
    return html_table.format(formatter)
