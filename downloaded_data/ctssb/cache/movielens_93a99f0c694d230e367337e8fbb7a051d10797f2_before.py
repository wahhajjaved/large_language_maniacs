# -*- coding: utf-8 -*-
from HTMLParser import HTMLParser
import requests
import sys

default_image_url = '/img/image_not_found.png'

reload(sys)
sys.setdefaultencoding('utf8')


class IMDBImgHTMLParser(HTMLParser):
    global default_image_url
    got_tag = False
    poster_img = default_image_url

    def handle_starttag(self, tag, attrs):
        if tag == 'div':
            if len(attrs) > 0 and attrs[0][0] == 'class' and attrs[0][1] == 'poster':
                self.got_tag = True
        elif self.got_tag is True and tag == 'img':
            for name, value in attrs:
                if name == 'src':
                    self.poster_img = value
                    self.got_tag = False

    def handle_endtag(self, tag):
        if tag == 'div':
            self.got_tag = False

    def get_img(self):
        return self.poster_img


class IMDBUrlHTMLParser(HTMLParser):
    got_tag = False
    movie_url = None
    find_count = 0
    base_url = 'http://www.imdb.com'

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            if len(attrs) > 0 and attrs[0][0] == 'class' and attrs[0][1] == 'findList':
                self.got_tag = True
        elif self.got_tag is True and self.find_count == 0 and tag == 'a':
            # return the first movie url from search result
            for name, value in attrs:
                if name == 'href':
                    self.movie_url = self.base_url + value
                    self.find_count += 1
                    self.got_tag = False

    def handle_endtag(self, tag):
        if tag == 'table':
            self.got_tag = False

    def get_movie_url(self):
        return self.movie_url


def get_movie_image(url=None):
    if url is None:
        return default_image_url
    """
    get url real url
    if url start with http://www.imdb.com/title/, find poster url from content
    if url start with http://www.imdb.com/find, find first find movie url than get its poster
    """
    r = requests.get(url)
    if r.url.startswith('http://www.imdb.com/title/'):
        parser = IMDBImgHTMLParser()
        parser.feed(r.content)
        return parser.get_img()
    elif r.url.startswith('http://www.imdb.com/find'):
        print r.url
        parser = IMDBUrlHTMLParser()
        parser.feed(r.content)
        new_url = parser.get_movie_url()
        if new_url is None:
            return default_image_url
        else:
            r = requests.get(new_url)
            parser = IMDBImgHTMLParser()
            parser.feed(r.content)
            return parser.get_img()
    return default_image_url
