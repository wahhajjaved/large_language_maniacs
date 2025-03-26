# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.conf.global_settings import TEMPLATE_STRING_IF_INVALID
from django.template.context import Context
from duck_inscription.models import SettingAnneeUni

__author__ = 'paul'
from django import template

register = template.Library()


def human_readable(value, arg):
    if hasattr(value, 'get_' + str(arg) + '_display'):
        return getattr(value, 'get_%s_display' % arg)()
    elif hasattr(value, str(arg)):
        if callable(getattr(value, str(arg))):
            return getattr(value, arg)()
        else:
            return getattr(value, arg)
    else:
        try:
            return value[arg]
        except KeyError:
            return TEMPLATE_STRING_IF_INVALID
register.filter('human_readable', human_readable)


@register.simple_tag
def annee_en_cour():
    annee = SettingAnneeUni.objects.annee_inscription_en_cours.cod_anu
    if annee:
        return "{} / {}".format(annee, int(annee) - 1)
    return "Fermé"

