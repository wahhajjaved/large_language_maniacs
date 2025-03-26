from urllib import urlencode
from lxml import html
from urlparse import urljoin

categories = ['images']

base_url = 'https://www.deviantart.com/'
search_url = base_url+'search?'

def request(query, params):
    global search_url
    params['url'] = search_url + urlencode({'q': query})
    return params


def response(resp):
    global base_url
    results = []
    if resp.status_code == 302:
        return results
    dom = html.fromstring(resp.text)
    for result in dom.xpath('//div[contains(@class, "tt-a tt-fh")]'):
        link = result.xpath('.//a[contains(@class, "thumb")]')[0]
        url = urljoin(base_url, link.attrib.get('href'))
        title_links = result.xpath('.//span[@class="details"]//a[contains(@class, "t")]')
        title = ''.join(title_links[0].xpath('.//text()'))
        content = html.tostring(link)+'<br />'+link.attrib.get('title', '')
        results.append({'url': url, 'title': title, 'content': content})
    return results
