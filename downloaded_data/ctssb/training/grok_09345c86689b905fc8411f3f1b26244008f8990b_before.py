from bs4 import BeautifulSoup


def strip_html(html):
    return ''.join(BeautifulSoup(html, 'html.parser').findAll(text=True))


def get_article_entry(item):
    for entry in item.get('body', []):
        keys = list(entry)
        if len(keys) > 0 and 'entry' in keys[0]:
            text = entry[keys[0]]
            entry_text = text.get('entrytext', 'no entrytext found')
            return strip_html(entry_text)


def get_article_title(item):
    entry_title = item.get('entryTitle', [])
    return strip_html(entry_title)
