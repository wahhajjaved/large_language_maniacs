# -*- coding: utf-8 -*-
from django.db.models import Q

from dictionary.models import Entry
from dictionary.models import Etymology
from dictionary.models import Example

def get_entries(form):
    entries = Entry.objects
    FILTER_PARAMS = {}
    FILTER_EXCLUDE_PARAMS = {}
    SORT_PARAMS = []
    PARSING_ERRORS = []

    # Сортировка
    DEFAULT_SORT = '-t'
    sortdir = form['sortdir']
    sortbase = form['sortbase']
    sort = sortdir + sortbase
    if not sort:
        sort = form['sort'] or DEFAULT_SORT
    VALID_SORT_PARAMS = {
        'alph': ('civil_equivalent', 'homonym_order'),
        '-alph': ('-civil_equivalent', '-homonym_order'),
        't': ('mtime', 'id'),
        '-t': ('-mtime', '-id'),
        }
    if sort in VALID_SORT_PARAMS:
        SORT_PARAMS = VALID_SORT_PARAMS[sort]
    else:
        PARSING_ERRORS.append('sort')

    # Статьи начинаются с
    find = form['find']
    if find:
        FILTER_PARAMS['civil_equivalent__istartswith'] = find


    def _set_enumerable_param(param, model_property=None):
        model_property = model_property or param
        value = form[param] or 'all'
        if value=='all':
            pass
        elif value=='none':
            FILTER_PARAMS[model_property + '__isnull'] = True
        elif value.isdigit():
            FILTER_PARAMS[model_property] = int(value)
        else:
            PARSING_ERRORS.append(param)

    # Автор статьи
    _set_enumerable_param('author', 'editor')

    # Статус статьи
    _set_enumerable_param('status')

    # Часть речи
    _set_enumerable_param('pos', 'part_of_speech')

    # Род
    _set_enumerable_param('gender')

    # Число
    _set_enumerable_param('tantum')

    # Тип имени собственного
    _set_enumerable_param('onym')

    # Каноническое имя
    _set_enumerable_param('canonical_name')

    # Притяжательность
    _set_enumerable_param('possessive')

    # Омонимы
    if form['homonym']:
        FILTER_PARAMS['homonym_order__isnull'] = False

    # Есть примечание
    if form['additional_info']:
        FILTER_EXCLUDE_PARAMS['additional_info'] = ''

    # Есть этимологии
    if form['etymology']:
        etyms = Etymology.objects.values_list('entry')
        FILTER_PARAMS['id__in'] = [item[0] for item in set(etyms)]

    # Статьи-дубликаты
    if form['duplicate']:
        FILTER_PARAMS['duplicate'] = True

    # Неизменяемое
    if form['uninflected']:
        FILTER_PARAMS['uninflected'] = True

    if PARSING_ERRORS:
        raise NameError('Недопустимые значения параметров: %s' % PARSING_ERRORS)

    entries = entries.filter(**FILTER_PARAMS)
    entries = entries.exclude(**FILTER_EXCLUDE_PARAMS)
    entries = entries.order_by(*SORT_PARAMS)

    return entries


def get_examples(form):
    examples = Example.objects
    entries = None
    FILTER_PARAMS = {}
    SORT_PARAMS = []
    PARSING_ERRORS = []

    # Сортировка
    DEFAULT_SORT = 'id'
    sortdir = form['hwSortdir']
    sortbase = form['hwSortbase']
    sort = sortdir + sortbase
    if not sort:
        sort = form['hwSort'] or DEFAULT_SORT
    VALID_SORT_PARAMS = {
        'id': ('id',),
        '-id': ('-id',),
        'addr': ('address_text', 'id'),
        '-addr': ('-address_text', '-id'),
        }
    if sort in VALID_SORT_PARAMS:
        SORT_PARAMS = VALID_SORT_PARAMS[sort]
    else:
        PARSING_ERRORS.append('sort')

    # Автор статьи
    value = form['hwAuthor'] or 'all'
    if value == 'all':
        pass
    elif value == 'none':
        entries = Entry.objects.filter(editor__isnull=True)
    elif value.isdigit():
        entries = Entry.objects.filter(editor__id=int(value))
    else:
        PARSING_ERRORS.append('hwAuthor')

    # Статьи начинаются с
    prfx = form['hwPrfx']
    if prfx:
        entries = entries or Entry.objects
        entries = entries.filter(civil_equivalent__istartswith=prfx)

    # Адреса начинаются на
    address = form['hwAddress']
    if address:
        FILTER_PARAMS['address_text__istartswith'] = address

    # Статус греческих параллелей
    greq_status = form['hwStatus'] or 'L'
    if greq_status == 'all':
        pass
    elif value.isalpha() and len(greq_status) == 1:
        FILTER_PARAMS['greek_eq_status'] = greq_status
    else:
        PARSING_ERRORS.append('hwStatus')

    if PARSING_ERRORS:
        raise NameError('Недопустимые значения параметров: %s' % PARSING_ERRORS)

    # CategoryValue для статусов статей
    good_statuses = [
            48, # поиск греч.
            46, # импортирована
            28, # завершена
            50, # редактируется
            29, # утверждена
            ]
    bad_statuses = [
            26, # создана
            27, # в работе
            ]
    # Примеры не должны попадать к грецисту, если статья имеет статус "создана" или
    # "в работе", за исключением тех случаев когда у примера выставлен
    # статус греческих параллелей "необходимы для определения значения" (M)
    # или "срочное" (U).
    if greq_status not in (u'M', u'U'):
        entries = entries or Entry.objects
        entries = entries.exclude(status__in=bad_statuses)

    if entries:
        examples = examples.filter(
            Q(meaning__entry_container__in=entries) |
            Q(meaning__parent_meaning__entry_container__in=entries) |
            Q(meaning__collogroup_container__base_meaning__entry_container__in=entries)
            )

    examples = examples.filter(**FILTER_PARAMS)
    examples = examples.order_by(*SORT_PARAMS)

    return examples
