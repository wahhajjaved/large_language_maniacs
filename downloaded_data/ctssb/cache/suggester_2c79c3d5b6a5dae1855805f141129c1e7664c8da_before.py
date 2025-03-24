# coding=utf-8

from collections import defaultdict
import cPickle as pickle
from itertools import groupby
import re
import struct


def default_tokenizer(s):
    s = s.lower()
    return _unique_list([
        t
        for t in _TOKEN_DELIMITER_REGEXP.split(s)
        if t
    ])


def infix_tokenizer(s):
    tokens = []
    for word in default_tokenizer(s):
        for i in range(len(word)):
            tokens.append(word[i:])
    return _unique_list(tokens)


class Suggester(object):

    def __init__(self, tokenizer=default_tokenizer, shard_size=500*1000, max_cached_items_count=20*1000, quality_multiplier=200, max_search_query_words=7, use_prefix_search_for_all_words=False):
        self._tokenizer = tokenizer
        self._shard_size = shard_size
        self._index_data = []
        self._cache = {}
        self._max_cached_items_count = max_cached_items_count
        self._quality_multiplier = quality_multiplier
        self._max_search_query_words = max_search_query_words
        self._use_prefix_search_for_all_words = use_prefix_search_for_all_words

    def suggest_keywords(self, search_query, limit=10):
        cache = self._cache
        result, cached_limit = cache.get(search_query, (None, None))
        if result is None or cached_limit < limit:
            result = _find_matched_suggestions(self._index_data, search_query, limit, self._quality_multiplier, self._max_search_query_words, self._use_prefix_search_for_all_words)
            cache[search_query] = (result, limit)
            while len(cache) > self._max_cached_items_count:
                cache.popitem()
        return result[:limit] if len(result) > limit else result

    def update_keywords(self, keywords_with_payloads):
        self._index_data = []
        self._cache = {}
        self._index_data = _generate_index_data(keywords_with_payloads, self._tokenizer, self._shard_size)

    def load_from_file(self, file_stream):
        self._index_data = []
        self._cache = {}
        self._index_data = pickle.load(file_stream)

    def dump_to_file(self, file_stream):
        pickle.dump(self._index_data, file_stream, pickle.HIGHEST_PROTOCOL)


_TOKEN_DELIMITER_REGEXP = re.compile('[-?!,"\'/[\\]\\.\\s{}&+<>;:|()_]+')
_NEWLINE_BYTEARRAY = bytearray(u'\n', 'utf-8')
_UINT32_PACKER = struct.Struct('>I')
_TOKEN_OFFSETS_PACKER = struct.Struct('>BI')


def _find_matched_suggestions(index_data, search_query, limit, quality_multiplier, max_search_query_words, use_prefix_search_for_all_words):
    words = default_tokenizer(unicode(search_query))[:max_search_query_words]
    if not words:
        return []
    if use_prefix_search_for_all_words:
        words = [w + u'*' for w in words]
    elif not (search_query.endswith(u' ') or words[-1].endswith(u'*')):
        words[-1] = words[-1] + u'*'
    suggestions = []
    quality_limit = limit * quality_multiplier
    for keywords, tokens, offsets_data in index_data:
        shard_suggestions = _get_suggested_keywords(keywords, tokens, offsets_data, words, quality_limit)
        suggestions.extend(shard_suggestions)
    return _adjust_suggestions_order(suggestions)[:limit]


def _generate_index_data(keywords_with_payloads, tokenizer, shard_size):
    index_data = []
    n = 0
    shard = []
    for kp in keywords_with_payloads:
        shard.append(kp)
        if len(shard) >= shard_size:
            index_data.append(_generate_keywords_index(shard, tokenizer))
            shard = []
        n += shard_size
    if shard:
        index_data.append(_generate_keywords_index(shard, tokenizer))
    return index_data


def _generate_keywords_index(keywords_with_payloads, tokenizer):
    tokens = []
    keywords_data = bytearray()
    for keyword, payload in keywords_with_payloads:
        if not keyword or u'\n' in keyword or u'\n' in payload:
            continue
        for i, token in enumerate(tokenizer(keyword)):
            if not token:
                continue
            if i > 0xff:
                break
            s = bytearray(_TOKEN_OFFSETS_PACKER.pack(i, len(keywords_data)))
            s.extend(bytearray(token, 'utf-8'))
            tokens.append(bytes(s))
        s = u'%s\n%s\n' % (keyword, payload)
        s = bytearray(s, 'utf-8')
        keywords_data.extend(s)
        if len(keywords_data) > 0xffffffff:
            raise Exception("Too big offset %d" % len(keywords_data))

    tokens.sort(key=lambda t: t[5:])
    tokens_data = bytearray(_NEWLINE_BYTEARRAY)
    offsets_data = bytearray()
    for token, token_group in groupby(tokens, key=lambda t: t[5:]):
        offset = len(offsets_data)
        token_group = sorted(token_group)
        offsets_data.extend(_UINT32_PACKER.pack(len(token_group)))
        for t in token_group:
            offsets_data.extend(t[:5])
        tokens_data.extend(bytearray(u'%08x' % offset, 'utf-8'))
        tokens_data.extend(token)
        tokens_data.extend(_NEWLINE_BYTEARRAY)

    return keywords_data, tokens_data, offsets_data


def _get_token_offset(tokens, word):
    tokens_len = len(tokens)
    lo = 1
    hi = tokens_len
    while True:
        n = (hi + lo) // 2
        n = tokens.rindex(_NEWLINE_BYTEARRAY, 0, n + 1) + 1
        pivot, nn = _get_next_line(tokens, n + 8)
        if word > pivot:
            if lo == n:
                break
            lo = n
        else:
            if hi == n:
                break
            hi = n
    while word > pivot:
        n = nn
        if n == hi:
            break
        pivot, nn = _get_next_line(tokens, n + 8)
    return n


def _get_word_offsets(tokens, offsets_data, word, limit):
    is_prefix_search = word.endswith(u'*')
    if is_prefix_search:
        word = word[:-1]
    word = bytearray(word, 'utf-8')
    word_len = len(word)
    n = _get_token_offset(tokens, word)
    offsets = []
    while n < len(tokens):
        pivot, nn = _get_next_line(tokens, n + 8)
        if (is_prefix_search and pivot[:word_len] != word) or (not is_prefix_search and pivot != word):
            break
        token_offset = int(tokens[n:n+8].decode('utf-8'), 16)
        offsets_count = _UINT32_PACKER.unpack(bytes(offsets_data[token_offset:token_offset+4]))[0]
        if offsets_count + len(offsets) > limit:
            offsets_count = limit - len(offsets)
        token_offset += 4
        offsets.extend(
            bytes(offsets_data[token_offset+i*5:token_offset+(i+1)*5])
            for i in range(offsets_count)
        )
        if len(offsets) >= limit:
            break
        n = nn
    return offsets


def _get_suggested_keywords(keywords, tokens, offsets_data, words, limit):
    offsets = []
    for word in words:
        word_offsets = _get_word_offsets(tokens, offsets_data, word, limit)
        if len(word_offsets) < limit:
            offsets = [word_offsets]
            break
        offsets.append(word_offsets)
    offsets = _intersect_offsets(offsets)
    keywords_with_payloads = _get_keywords_with_payloads(keywords, offsets, words)
    return keywords_with_payloads


def _intersect_offsets(offsets):
    unique_offsets = frozenset.intersection(*[
        frozenset(x[1:] for x in ff)
        for ff in offsets
    ])
    weighted_offsets = defaultdict(list)
    for word_offsets in offsets:
        for offset in word_offsets:
            k = offset[1:]
            if k in unique_offsets:
                weighted_offsets[k].append(ord(offset[0]))
    offsets = sorted((sorted(v), k) for k, v in weighted_offsets.items())
    return [k for _, k in offsets]


def _get_keywords_with_payloads(keywords, offsets, words):
    words = [_clean_trailing_stars(w) for w in words]
    keywords_with_payloads = []
    for offset in offsets:
        offset = _UINT32_PACKER.unpack(offset)[0]
        keyword, offset = _get_next_line(keywords, offset)
        keyword = keyword.decode('utf-8')
        keyword_lower = keyword.lower()
        weights = sorted(keyword_lower.find(w) for w in words)
        if weights[0] == -1:
            continue
        weights.append(len(keyword))
        payload, _ = _get_next_line(keywords, offset)
        payload = payload.decode('utf-8')
        keywords_with_payloads.append((weights, keyword, payload))
    return keywords_with_payloads


def _clean_trailing_stars(w):
    while w.endswith(u'*'):
        w = w[:-1]
    return w


def _adjust_suggestions_order(suggestions):
    suggestions.sort(key=lambda x: x[0])
    return [
        (keyword, payload)
        for _, keyword, payload in suggestions
    ]


def _get_next_line(s, start_offset):
    end_offset = s.index(_NEWLINE_BYTEARRAY, start_offset)
    return s[start_offset:end_offset], end_offset + 1


def _unique_list(xx):
    used_items = set()
    yy = []
    for x in xx:
        if x not in used_items:
            yy.append(x)
            used_items.add(x)
    return yy

