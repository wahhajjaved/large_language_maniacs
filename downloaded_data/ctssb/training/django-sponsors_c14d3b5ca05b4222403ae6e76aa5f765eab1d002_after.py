# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from ..models import Sponsor
from django import template

register = template.Library()


@register.inclusion_tag('sponsors/sponsors_tag.html')
def show_sponsors(sponsor_type=None):
    if sponsor_type:
        types_names = sponsor_type.split(',')

        ret = {}
        for name in types_names:
            ret['sponsors_'+name] = Sponsor.objects.filter(category=Sponsor.SPONSOR_CATEGORIES_REV[name.upper()])

        return ret

    return {'sponsors': Sponsor.get_all_sponsors()}

