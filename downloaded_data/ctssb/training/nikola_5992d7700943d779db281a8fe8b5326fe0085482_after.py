# -*- coding: utf-8 -*-

# Copyright © 2012-2014 Roberto Alsina and others.

# Permission is hereby granted, free of charge, to any
# person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the
# Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the
# Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice
# shall be included in all copies or substantial portions of
# the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
# KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
# PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
# OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from __future__ import unicode_literals, print_function, absolute_import

import io
from collections import defaultdict
import datetime
import os
import re
import string
try:
    from urlparse import urljoin
except ImportError:
    from urllib.parse import urljoin  # NOQA

import dateutil.tz
import lxml.html
import natsort
try:
    import pyphen
except ImportError:
    pyphen = None

from math import ceil

# for tearDown with _reload we cannot use 'from import' to get forLocaleBorg
import nikola.utils
from .utils import (
    bytes_str,
    current_time,
    Functionary,
    LOGGER,
    LocaleBorg,
    slugify,
    to_datetime,
    unicode_str,
    demote_headers,
    get_translation_candidate,
    unslugify,
)
from .rc4 import rc4

__all__ = ['Post']

TEASER_REGEXP = re.compile('<!--\s*TEASER_END(:(.+))?\s*-->', re.IGNORECASE)


class Post(object):

    """Represents a blog post or web page."""

    def __init__(
        self,
        source_path,
        config,
        destination,
        use_in_feeds,
        messages,
        template_name,
        compiler
    ):
        """Initialize post.

        The source path is the user created post file. From it we calculate
        the meta file, as well as any translations available, and
        the .html fragment file path.
        """
        self.config = config
        self.compiler = compiler
        self.compile_html = self.compiler.compile_html
        self.demote_headers = self.compiler.demote_headers and self.config['DEMOTE_HEADERS']
        tzinfo = self.config['__tzinfo__']
        if self.config['FUTURE_IS_NOW']:
            self.current_time = None
        else:
            self.current_time = current_time()
        self.translated_to = set([])
        self._prev_post = None
        self._next_post = None
        self.base_url = self.config['BASE_URL']
        self.is_draft = False
        self.is_private = False
        self.is_mathjax = False
        self.strip_indexes = self.config['STRIP_INDEXES']
        self.index_file = self.config['INDEX_FILE']
        self.pretty_urls = self.config['PRETTY_URLS']
        self.source_path = source_path  # posts/blah.txt
        self.post_name = os.path.splitext(source_path)[0]  # posts/blah
        # cache[\/]posts[\/]blah.html
        self.base_path = os.path.join(self.config['CACHE_FOLDER'], self.post_name + ".html")
        # cache/posts/blah.html
        self._base_path = self.base_path.replace('\\', '/')
        self.metadata_path = self.post_name + ".meta"  # posts/blah.meta
        self.folder = destination
        self.translations = self.config['TRANSLATIONS']
        self.default_lang = self.config['DEFAULT_LANG']
        self.messages = messages
        self.skip_untranslated = not self.config['SHOW_UNTRANSLATED_POSTS']
        self._template_name = template_name
        self.is_two_file = True
        self.hyphenate = self.config['HYPHENATE']
        self._reading_time = None
        self._remaining_reading_time = None
        self._paragraph_count = None
        self._remaining_paragraph_count = None

        default_metadata = get_meta(self, self.config['FILE_METADATA_REGEXP'], self.config['UNSLUGIFY_TITLES'])

        self.meta = Functionary(lambda: None, self.default_lang)
        self.meta[self.default_lang] = default_metadata

        # Load internationalized metadata
        for lang in self.translations:
            if os.path.isfile(get_translation_candidate(self.config, self.source_path, lang)):
                self.translated_to.add(lang)
            if lang != self.default_lang:
                meta = defaultdict(lambda: '')
                meta.update(default_metadata)
                meta.update(get_meta(self, self.config['FILE_METADATA_REGEXP'], self.config['UNSLUGIFY_TITLES'], lang))
                self.meta[lang] = meta

        if not self.is_translation_available(self.default_lang):
            # Special case! (Issue #373)
            # Fill default_metadata with stuff from the other languages
            for lang in sorted(self.translated_to):
                default_metadata.update(self.meta[lang])

        if 'date' not in default_metadata and not use_in_feeds:
            # For stories we don't *really* need a date
            if self.config['__invariant__']:
                default_metadata['date'] = datetime.datetime(2013, 12, 31, 23, 59, 59, tzinfo=tzinfo)
            else:
                default_metadata['date'] = datetime.datetime.utcfromtimestamp(
                    os.stat(self.source_path).st_ctime).replace(tzinfo=dateutil.tz.tzutc()).astimezone(tzinfo)

        if 'title' not in default_metadata or 'slug' not in default_metadata \
                or 'date' not in default_metadata:
            raise OSError("You must set a title (found '{0}'), a slug (found "
                          "'{1}') and a date (found '{2}')! [in file "
                          "{3}]".format(default_metadata.get('title', None),
                                        default_metadata.get('slug', None),
                                        default_metadata.get('date', None),
                                        source_path))

        if 'type' not in default_metadata:
            # default value is 'text'
            default_metadata['type'] = 'text'

        # If time zone is set, build localized datetime.
        self.date = to_datetime(self.meta[self.default_lang]['date'], tzinfo)

        self.publish_later = False if self.current_time is None else self.date >= self.current_time

        is_draft = False
        is_private = False
        self._tags = {}
        for lang in self.translated_to:
            self._tags[lang] = natsort.natsorted(
                list(set([x.strip() for x in self.meta[lang]['tags'].split(',')])))
            self._tags[lang] = [t for t in self._tags[lang] if t]
            if 'draft' in self._tags[lang]:
                is_draft = True
                LOGGER.debug('The post "{0}" is a draft.'.format(self.source_path))
                self._tags[lang].remove('draft')

            # TODO: remove in v8
            if 'retired' in self._tags[lang]:
                is_private = True
                LOGGER.warning('The "retired" tag in post "{0}" is now deprecated and will be removed in v8.  Use "private" instead.'.format(self.source_path))
                self._tags[lang].remove('retired')
            # end remove in v8

            if 'private' in self._tags[lang]:
                is_private = True
                LOGGER.debug('The post "{0}" is private.'.format(self.source_path))
                self._tags[lang].remove('private')

        # While draft comes from the tags, it's not really a tag
        self.is_draft = is_draft
        self.is_private = is_private
        self.is_post = use_in_feeds
        self.use_in_feeds = use_in_feeds and not is_draft and not is_private \
            and not self.publish_later

        # If mathjax is a tag, then enable mathjax rendering support
        self.is_mathjax = 'mathjax' in self.tags

    def __repr__(self):
        return '<Post: {0}>'.format(self.source_path)

    def _has_pretty_url(self, lang):
        if self.pretty_urls and \
                self.meta[lang].get('pretty_url', '') != 'False' and \
                self.meta[lang]['slug'] != 'index':
            return True
        else:
            return False

    @property
    def alltags(self):
        """This is ALL the tags for this post."""
        tags = []
        for l in self._tags:
            tags.extend(self._tags[l])
        return list(set(tags))

    @property
    def tags(self):
        lang = nikola.utils.LocaleBorg().current_lang
        if lang in self._tags:
            return self._tags[lang]
        elif self.default_lang in self._tags:
            return self._tags[self.default_lang]
        else:
            return []

    @property
    def prev_post(self):
        lang = nikola.utils.LocaleBorg().current_lang
        rv = self._prev_post
        while self.skip_untranslated:
            if rv is None:
                break
            if rv.is_translation_available(lang):
                break
            rv = rv._prev_post
        return rv

    @prev_post.setter  # NOQA
    def prev_post(self, v):
        self._prev_post = v

    @property
    def next_post(self):
        lang = nikola.utils.LocaleBorg().current_lang
        rv = self._next_post
        while self.skip_untranslated:
            if rv is None:
                break
            if rv.is_translation_available(lang):
                break
            rv = rv._next_post
        return rv

    @next_post.setter  # NOQA
    def next_post(self, v):
        self._next_post = v

    @property
    def template_name(self):
        return self.meta('template') or self._template_name

    def formatted_date(self, date_format):
        """Return the formatted date, as unicode."""
        fmt_date = self.date.strftime(date_format)
        # Issue #383, this changes from py2 to py3
        if isinstance(fmt_date, bytes_str):
            fmt_date = fmt_date.decode('utf8')
        return fmt_date

    def title(self, lang=None):
        """Return localized title.

        If lang is not specified, it defaults to the current language from
        templates, as set in LocaleBorg.
        """
        if lang is None:
            lang = nikola.utils.LocaleBorg().current_lang
        return self.meta[lang]['title']

    def author(self, lang=None):
        """Return localized author or BLOG_AUTHOR if unspecified.

        If lang is not specified, it defaults to the current language from
        templates, as set in LocaleBorg.
        """
        if lang is None:
            lang = nikola.utils.LocaleBorg().current_lang
        if self.meta[lang]['author']:
            author = self.meta[lang]['author']
        else:
            author = self.config['BLOG_AUTHOR'](lang)

        return author

    def description(self, lang=None):
        """Return localized description."""
        if lang is None:
            lang = nikola.utils.LocaleBorg().current_lang
        return self.meta[lang]['description']

    def deps(self, lang):
        """Return a list of dependencies to build this post's page."""
        deps = []
        if self.default_lang in self.translated_to:
            deps.append(self.base_path)
            deps.append(self.source_path)
        if lang != self.default_lang:
            cand_1 = get_translation_candidate(self.config, self.source_path, lang)
            cand_2 = get_translation_candidate(self.config, self.base_path, lang)
            if os.path.exists(cand_1):
                deps.extend([cand_1, cand_2])
        return deps

    def compile(self, lang):
        """Generate the cache/ file with the compiled post."""

        def wrap_encrypt(path, password):
            """Wrap a post with encryption."""
            with io.open(path, 'r+', encoding='utf8') as inf:
                data = inf.read() + "<!--tail-->"
            data = CRYPT.substitute(data=rc4(password, data))
            with io.open(path, 'w+', encoding='utf8') as outf:
                outf.write(data)

        dest = self.translated_base_path(lang)
        if not self.is_translation_available(lang) and not self.config['SHOW_UNTRANSLATED_POSTS']:
            return
        # Set the language to the right thing
        LocaleBorg().set_locale(lang)
        self.compile_html(
            self.translated_source_path(lang),
            dest,
            self.is_two_file),
        if self.meta('password'):
            wrap_encrypt(dest, self.meta('password'))
        if self.publish_later:
            LOGGER.notice('{0} is scheduled to be published in the future ({1})'.format(
                self.source_path, self.date))

    def extra_deps(self):
        """get extra depepencies from .dep files
        This file is created by ReST
        """
        dep_path = self.base_path + '.dep'
        if os.path.isfile(dep_path):
            with io.open(dep_path, 'r+', encoding='utf8') as depf:
                return [l.strip() for l in depf.readlines()]
        return []

    def fragment_deps(self, lang):
        """Return a list of dependencies to build this post's fragment."""
        deps = []
        if self.default_lang in self.translated_to:
            deps.append(self.source_path)
        if os.path.isfile(self.metadata_path):
            deps.append(self.metadata_path)
        deps.extend(self.extra_deps())
        lang_deps = []
        if lang != self.default_lang:
            lang_deps = [get_translation_candidate(self.config, d, lang) for d in deps]
            deps += lang_deps
        return [d for d in deps if os.path.exists(d)]

    def is_translation_available(self, lang):
        """Return true if the translation actually exists."""
        return lang in self.translated_to

    def translated_source_path(self, lang):
        """Return path to the translation's source file."""
        if lang in self.translated_to:
            if lang == self.default_lang:
                return self.source_path
            else:
                return get_translation_candidate(self.config, self.source_path, lang)
        elif lang != self.default_lang:
            return self.source_path
        else:
            return get_translation_candidate(self.config, self.source_path, sorted(self.translated_to)[0])

    def translated_base_path(self, lang):
        """Return path to the translation's base_path file."""
        return get_translation_candidate(self.config, self.base_path, lang)

    def _translated_file_path(self, lang):
        """Return path to the translation's file, or to the original."""
        if lang in self.translated_to:
            if lang == self.default_lang:
                return self.base_path
            else:
                return get_translation_candidate(self.config, self.base_path, lang)
        elif lang != self.default_lang:
            return self.base_path
        else:
            return get_translation_candidate(self.config, self.base_path, sorted(self.translated_to)[0])

    def text(self, lang=None, teaser_only=False, strip_html=False, show_read_more_link=True, rss_read_more_link=False):
        """Read the post file for that language and return its contents.

        teaser_only=True breaks at the teaser marker and returns only the teaser.
        strip_html=True removes HTML tags
        show_read_more_link=False does not add the Read more... link
        rss_read_more_link=True uses RSS_READ_MORE_LINK instead of INDEX_READ_MORE_LINK
        lang=None uses the last used to set locale

        All links in the returned HTML will be relative.
        The HTML returned is a bare fragment, not a full document.
        """

        if lang is None:
            lang = nikola.utils.LocaleBorg().current_lang
        file_name = self._translated_file_path(lang)
        with io.open(file_name, "r", encoding="utf8") as post_file:
            data = post_file.read().strip()
        if self.compiler.extension() == '.php':
            return data
        try:
            document = lxml.html.fragment_fromstring(data, "body")
        except lxml.etree.ParserError as e:
            # if we don't catch this, it breaks later (Issue #374)
            if str(e) == "Document is empty":
                return ""
            # let other errors raise
            raise(e)
        base_url = self.permalink(lang=lang)
        document.make_links_absolute(base_url)

        if self.hyphenate:
            hyphenate(document, lang)

        try:
            data = lxml.html.tostring(document.body, encoding='unicode')
        except:
            data = lxml.html.tostring(document, encoding='unicode')

        if teaser_only:
            teaser = TEASER_REGEXP.split(data)[0]
            if teaser != data:
                if not strip_html and show_read_more_link:
                    if TEASER_REGEXP.search(data).groups()[-1]:
                        teaser += '<p class="more"><a href="{0}">{1}</a></p>'.format(
                            self.permalink(lang),
                            TEASER_REGEXP.search(data).groups()[-1])
                    else:
                        l = self.config['RSS_READ_MORE_LINK'](lang) if rss_read_more_link else self.config['INDEX_READ_MORE_LINK'](lang)
                        teaser += l.format(
                            link=self.permalink(lang),
                            read_more=self.messages[lang]["Read more"],
                            min_remaining_read=self.messages[lang]["%d min remaining to read"] % (self.remaining_reading_time),
                            reading_time=self.reading_time,
                            remaining_reading_time=self.remaining_reading_time,
                            paragraph_count=self.paragraph_count,
                            remaining_paragraph_count=self.remaining_paragraph_count)
                # This closes all open tags and sanitizes the broken HTML
                document = lxml.html.fromstring(teaser)
                try:
                    data = lxml.html.tostring(document.body, encoding='unicode')
                except IndexError:
                    data = lxml.html.tostring(document, encoding='unicode')

        if data and strip_html:
            try:
                # Not all posts have a body. For example, you may have a page statically defined in the template that does not take content as input.
                content = lxml.html.fromstring(data)
                data = content.text_content().strip()  # No whitespace wanted.
            except lxml.etree.ParserError:
                data = ""
        elif data:
            if self.demote_headers:
                # see above
                try:
                    document = lxml.html.fromstring(data)
                    demote_headers(document, self.demote_headers)
                    data = lxml.html.tostring(document.body, encoding='unicode')
                except (lxml.etree.ParserError, IndexError):
                    data = lxml.html.tostring(document, encoding='unicode')

        return data

    @property
    def reading_time(self):
        """Reading time based on length of text."""
        if self._reading_time is None:
            text = self.text(strip_html=True)
            words_per_minute = 220
            words = len(text.split())
            self._reading_time = int(ceil(words / words_per_minute)) or 1
        return self._reading_time

    @property
    def remaining_reading_time(self):
        """Remaining reading time based on length of text (does not include teaser)."""
        if self._remaining_reading_time is None:
            text = self.text(teaser_only=True, strip_html=True)
            words_per_minute = 220
            words = len(text.split())
            self._remaining_reading_time = self.reading_time - int(ceil(words / words_per_minute)) or 1
        return self._remaining_reading_time

    @property
    def paragraph_count(self):
        """Return the paragraph count for this post."""
        if self._paragraph_count is None:
            # duplicated with Post.text()
            lang = nikola.utils.LocaleBorg().current_lang
            file_name = self._translated_file_path(lang)
            with io.open(file_name, "r", encoding="utf8") as post_file:
                data = post_file.read().strip()
            try:
                document = lxml.html.fragment_fromstring(data, "body")
            except lxml.etree.ParserError as e:
                # if we don't catch this, it breaks later (Issue #374)
                if str(e) == "Document is empty":
                    return ""
                # let other errors raise
                raise(e)

            # output is a float, for no real reason at all
            self._paragraph_count = int(document.xpath('count(//p)'))
        return self._paragraph_count

    @property
    def remaining_paragraph_count(self):
        """Return the remaining paragraph count for this post (does not include teaser)."""
        if self._remaining_paragraph_count is None:
            try:
                # Just asking self.text() is easier here.
                document = lxml.html.fragment_fromstring(self.text(teaser_only=True, show_read_more_link=False), "body")
            except lxml.etree.ParserError as e:
                # if we don't catch this, it breaks later (Issue #374)
                if str(e) == "Document is empty":
                    return ""
                # let other errors raise
                raise(e)

            self._remaining_paragraph_count = self.paragraph_count - int(document.xpath('count(//p)'))
        return self._remaining_paragraph_count

    def source_link(self, lang=None):
        """Return absolute link to the post's source."""
        ext = self.source_ext(True)
        return "/" + self.destination_path(
            lang=lang,
            extension=ext,
            sep='/')

    def destination_path(self, lang=None, extension='.html', sep=os.sep):
        """Destination path for this post, relative to output/.

        If lang is not specified, it's the current language.
        Extension is used in the path if specified.
        """
        if lang is None:
            lang = nikola.utils.LocaleBorg().current_lang
        if self._has_pretty_url(lang):
            path = os.path.join(self.translations[lang],
                                self.folder, self.meta[lang]['slug'], 'index' + extension)
        else:
            path = os.path.join(self.translations[lang],
                                self.folder, self.meta[lang]['slug'] + extension)
        if sep != os.sep:
            path = path.replace(os.sep, sep)
        return path

    def permalink(self, lang=None, absolute=False, extension='.html'):
        if lang is None:
            lang = nikola.utils.LocaleBorg().current_lang

        # Let compilers override extension (e.g. the php compiler)
        if self.compiler.extension() != '.html':
            extension = self.compiler.extension()

        pieces = self.translations[lang].split(os.sep)
        pieces += self.folder.split(os.sep)
        if self._has_pretty_url(lang):
            pieces += [self.meta[lang]['slug'], 'index' + extension]
        else:
            pieces += [self.meta[lang]['slug'] + extension]
        pieces = [_f for _f in pieces if _f and _f != '.']
        link = '/' + '/'.join(pieces)
        if absolute:
            link = urljoin(self.base_url, link[1:])
        index_len = len(self.index_file)
        if self.strip_indexes and link[-(1 + index_len):] == '/' + self.index_file:
            return link[:-index_len]
        else:
            return link

    @property
    def previewimage(self, lang=None):
        if lang is None:
            lang = nikola.utils.LocaleBorg().current_lang

        image_path = self.meta[lang]['previewimage']

        if not image_path:
            return None

        return urljoin(self.base_url, image_path)

    def source_ext(self, prefix=False):
        """
        Return the source file extension.

        If `prefix` is True, a `.src.` prefix will be added to the resulting extension
        if it’s equal to the destination extension.
        """

        ext = os.path.splitext(self.source_path)[1]
        # do not publish PHP sources
        if prefix and ext == '.html':
            # ext starts with a dot
            return '.src' + ext
        else:
            return ext

# Code that fetches metadata from different places


def re_meta(line, match=None):
    """re.compile for meta"""
    if match:
        reStr = re.compile('^\.\. {0}: (.*)'.format(re.escape(match)))
    else:
        reStr = re.compile('^\.\. (.*?): (.*)')
    result = reStr.findall(line.strip())
    if match and result:
        return (match, result[0])
    elif not match and result:
        return (result[0][0], result[0][1].strip())
    else:
        return (None,)


def _get_metadata_from_filename_by_regex(filename, metadata_regexp, unslugify_titles):
    """
    Tries to ried the metadata from the filename based on the given re.
    This requires to use symbolic group names in the pattern.

    The part to read the metadata from the filename based on a regular
    expression is taken from Pelican - pelican/readers.py
    """
    match = re.match(metadata_regexp, filename)
    meta = {}

    if match:
        # .items() for py3k compat.
        for key, value in match.groupdict().items():
            k = key.lower().strip()  # metadata must be lowercase
            if k == 'title' and unslugify_titles:
                meta[k] = unslugify(value, discard_numbers=False)
            else:
                meta[k] = value

    return meta


def get_metadata_from_file(source_path, config=None, lang=None):
    """Extracts metadata from the file itself, by parsing contents."""
    try:
        if lang and config:
            source_path = get_translation_candidate(config, source_path, lang)
        elif lang:
            source_path += '.' + lang
        with io.open(source_path, "r", encoding="utf8") as meta_file:
            meta_data = [x.strip() for x in meta_file.readlines()]
        return _get_metadata_from_file(meta_data)
    except (UnicodeDecodeError, UnicodeEncodeError):
        raise ValueError('Error reading {0}: Nikola only supports UTF-8 files'.format(source_path))
    except Exception:  # The file may not exist, for multilingual sites
        return {}


def _get_metadata_from_file(meta_data):
    """Parse file contents and obtain metadata.

    >>> g = _get_metadata_from_file
    >>> list(g([]).values())
    []
    >>> str(g(["FooBar","======"])["title"])
    'FooBar'
    >>> str(g(["#FooBar"])["title"])
    'FooBar'
    >>> str(g([".. title: FooBar"])["title"])
    'FooBar'
    >>> 'title' in g(["","",".. title: FooBar"])
    False
    >>> 'title' in g(["",".. title: FooBar"])  # for #520
    True

    """
    meta = {}

    re_md_title = re.compile(r'^{0}([^{0}].*)'.format(re.escape('#')))
    # Assuming rst titles are going to be at least 4 chars long
    # otherwise this detects things like ''' wich breaks other markups.
    re_rst_title = re.compile(r'^([{0}]{{4,}})'.format(re.escape(
        string.punctuation)))

    for i, line in enumerate(meta_data):
        # txt2tags requires an empty line at the beginning
        # and since we are here because it's a 1-file post
        # let's be flexible on what we accept, so, skip empty
        # first lines.
        if not line and i > 0:
            break
        if 'title' not in meta:
            match = re_meta(line, 'title')
            if match[0]:
                meta['title'] = match[1]
        if 'title' not in meta:
            if re_rst_title.findall(line) and i > 0:
                meta['title'] = meta_data[i - 1].strip()
        if 'title' not in meta:
            if re_md_title.findall(line):
                meta['title'] = re_md_title.findall(line)[0]

        match = re_meta(line)
        if match[0]:
            meta[match[0]] = match[1]

    return meta


def get_metadata_from_meta_file(path, config=None, lang=None):
    """Takes a post path, and gets data from a matching .meta file."""
    meta_path = os.path.splitext(path)[0] + '.meta'
    if lang and config:
        meta_path = get_translation_candidate(config, meta_path, lang)
    elif lang:
        meta_path += '.' + lang
    if os.path.isfile(meta_path):
        with io.open(meta_path, "r", encoding="utf8") as meta_file:
            meta_data = meta_file.readlines()

        # Detect new-style metadata.
        newstyleregexp = re.compile(r'\.\. .*?: .*')
        newstylemeta = False
        for l in meta_data:
            if l.strip():
                if re.match(newstyleregexp, l):
                    newstylemeta = True

        if newstylemeta:
            # New-style metadata is basically the same as reading metadata from
            # a 1-file post.
            return get_metadata_from_file(path, config, lang)
        else:
            while len(meta_data) < 7:
                meta_data.append("")
            (title, slug, date, tags, link, description, _type) = [
                x.strip() for x in meta_data][:7]

            meta = {}

            if title:
                meta['title'] = title
            if slug:
                meta['slug'] = slug
            if date:
                meta['date'] = date
            if tags:
                meta['tags'] = tags
            if link:
                meta['link'] = link
            if description:
                meta['description'] = description
            if _type:
                meta['type'] = _type

            return meta

    elif lang:
        # Metadata file doesn't exist, but not default language,
        # So, if default language metadata exists, return that.
        # This makes the 2-file format detection more reliable (Issue #525)
        return get_metadata_from_meta_file(path, config, lang=None)
    else:
        return {}


def get_meta(post, file_metadata_regexp=None, unslugify_titles=False, lang=None):
    """Get post's meta from source.

    If ``file_metadata_regexp`` is given it will be tried to read
    metadata from the filename.
    If ``unslugify_titles`` is True, the extracted title (if any) will be unslugified, as is done in galleries.
    If any metadata is then found inside the file the metadata from the
    file will override previous findings.
    """
    meta = defaultdict(lambda: '')

    try:
        config = post.config
    except AttributeError:
        config = None

    meta.update(get_metadata_from_meta_file(post.metadata_path, config, lang))

    if meta:
        return meta
    post.is_two_file = False

    if file_metadata_regexp is not None:
        meta.update(_get_metadata_from_filename_by_regex(post.source_path,
                                                         file_metadata_regexp,
                                                         unslugify_titles))

    meta.update(get_metadata_from_file(post.source_path, config, lang))

    if lang is None:
        # Only perform these checks for the default language

        if 'slug' not in meta:
            # If no slug is found in the metadata use the filename
            meta['slug'] = slugify(unicode_str(os.path.splitext(
                os.path.basename(post.source_path))[0]))

        if 'title' not in meta:
            # If no title is found, use the filename without extension
            meta['title'] = os.path.splitext(
                os.path.basename(post.source_path))[0]

    return meta


def hyphenate(dom, lang):
    if pyphen is not None:
        hyphenator = pyphen.Pyphen(lang=lang)
        for tag in ('p', 'li', 'span'):
            for node in dom.xpath("//%s[not(parent::pre)]" % tag):
                math_found = False
                if node.getchildren():
                    for child in node.getchildren():
                        if child.tag == 'span' and 'math' in child.get('class', []):
                            math_found = True
                else:
                    if 'math' in node.get('class', []):
                        math_found = True
                if not math_found:
                    insert_hyphens(node, hyphenator)
    return dom


def insert_hyphens(node, hyphenator):
    textattrs = ('text', 'tail')
    if isinstance(node, lxml.etree._Entity):
        # HTML entities have no .text
        textattrs = ('tail',)
    for attr in textattrs:
        text = getattr(node, attr)
        if not text:
            continue
        new_data = ' '.join([hyphenator.inserted(w, hyphen='\u00AD')
                             for w in text.split(' ')])
        # Spaces are trimmed, we have to add them manually back
        if text[0].isspace():
            new_data = ' ' + new_data
        if text[-1].isspace():
            new_data += ' '
        setattr(node, attr, new_data)

    for child in node.iterchildren():
        insert_hyphens(child, hyphenator)


CRYPT = string.Template("""\
<script>
function rc4(key, str) {
    var s = [], j = 0, x, res = '';
    for (var i = 0; i < 256; i++) {
        s[i] = i;
    }
    for (i = 0; i < 256; i++) {
        j = (j + s[i] + key.charCodeAt(i % key.length)) % 256;
        x = s[i];
        s[i] = s[j];
        s[j] = x;
    }
    i = 0;
    j = 0;
    for (var y = 0; y < str.length; y++) {
        i = (i + 1) % 256;
        j = (j + s[i]) % 256;
        x = s[i];
        s[i] = s[j];
        s[j] = x;
        res += String.fromCharCode(str.charCodeAt(y) ^ s[(s[i] + s[j]) % 256]);
    }
    return res;
}
function decrypt() {
    key = $$("#key").val();
    crypt_div = $$("#encr")
    crypted = crypt_div.html();
    decrypted = rc4(key, window.atob(crypted));
    if (decrypted.substr(decrypted.length - 11) == "<!--tail-->"){
        crypt_div.html(decrypted);
        $$("#pwform").hide();
        crypt_div.show();
    } else { alert("Wrong password"); };
}
</script>

<div id="encr" style="display: none;">${data}</div>
<div id="pwform">
<form onsubmit="javascript:decrypt(); return false;" class="form-inline">
<fieldset>
<legend>This post is password-protected.</legend>
<input type="password" id="key" placeholder="Type password here">
<button type="submit" class="btn">Show Content</button>
</fieldset>
</form>
</div>""")
