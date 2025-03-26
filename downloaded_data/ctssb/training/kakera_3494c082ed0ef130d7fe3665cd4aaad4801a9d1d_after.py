# Some of these are shamelessly stolen from the wagtail demo project:
# https://github.com/torchbox/wagtaildemo/blob/master/demo/templatetags/demo_tags.py
import re
from django import template

register = template.Library()

@register.simple_tag
def get_site_theme(site):
    return site.themes.filter(active=True).first()

@register.simple_tag
def get_site_settings(site):
    return site.settings.first()

@register.simple_tag(takes_context=True)
def absolute_media_url(context, url):
    if url.startswith('/'):
        return context['request'].build_absolute_uri(url)
    return url

@register.filter()
def force_https(url):
    if url.startswith('http://'):
        return "https" + url[4:]
    return url

@register.filter()
def force_http(url):
    if url.startswith('https://'):
        return "http" + url[5:]
    return url

# PARSE MARKDOWN WITH REGEX
MARKDOWN_LINEBREAKS_RE = re.compile(r'(?<!\n)\n(?!\n)', flags=re.MULTILINE)
@register.filter(is_safe=True)
def markdown_linebreaks(s):
    return MARKDOWN_LINEBREAKS_RE.sub('<br/>\n', s.strip())
