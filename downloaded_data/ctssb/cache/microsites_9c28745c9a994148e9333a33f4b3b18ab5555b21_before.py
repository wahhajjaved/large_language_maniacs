# encoding=utf-8

from django import template

register = template.Library()


@register.filter(name='soilID')
def soilID(sample):
    barcode = sample.get('sample_id_sample_barcode_id', None)
    if barcode:
        return barcode
    return sample.get('sample_id_sample_manual_id', '')