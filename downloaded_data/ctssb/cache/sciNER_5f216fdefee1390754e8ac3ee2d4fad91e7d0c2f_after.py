"""

"""


from typing import List, Tuple, Mapping, Callable, Set, Union
from numbers import Integral
from chempred.chemdner import Annotation, Interval
from itertools import chain

import numpy as np


PADDING_VAL = 0
MAXCHAR = 127
Sampler = Callable[[int, List[Annotation]], List[List[Annotation]]]


def slide(center: int, width: int, lastpos: int, flanking: bool) \
        -> List[Interval]:
    """
    :param center:
    :param width:
    :param lastpos:
    :param flanking:
    >>> slide(-1, 3, 10, True)
    [(0, 3)]
    >>> slide(0, 3, 10, False)
    [(0, 3)]
    >>> slide(0, 3, 10, True)
    [(0, 3), (1, 4)]
    >>> slide(8, 3, 10, False)
    [(6, 9), (7, 10)]
    >>> slide(8, 3, 10, True)
    [(5, 8), (6, 9), (7, 10)]
    >>> slide(10, 3, 10, False)
    []
    >>> slide(10, 3, 10, True)
    [(7, 10)]
    >>> slide(0, 10, 10, False) == slide(0, 10, 10, True) == [(0, 10)]
    True
    >>> slide(0, 11, 10, False) == slide(0, 11, 10, True) == []
    True
    """
    first = max(center - (width if flanking else width - 1), 0)
    last = min(center + 2 if flanking else center + 1, lastpos - width + 1)
    return [(i, i + width) for i in range(first, last)]


def make_sampler(width: int, maxlen: int, flanking: bool) \
        -> Sampler:
    """
    :type width: int
    :param width: the desired number of context tokens to sample; e.g. for a
    positive token at index `i` and window `3` the function will try to create
    samples [(i-2, i-1, i), (i-1, i, i+1), (i, i+1, i+2)] if flanking == False
    :param maxlen: the maximum length of a sample in unicode codes.
    :type flanking: bool
    :param flanking: include windows adjacent to central words; note that
    each positive token is an independent central word
    >>> text = "abcdefjhijklmnop"
    >>> extractor = lambda x: text[x[0].start: x[-1].end]
    >>> annotations = [Annotation(None, 0, 4, None, None),
    ...                Annotation(None, 5, 8, None, None),
    ...                Annotation(None, 8, 10, None, None),
    ...                Annotation(None, 11, 12, None, None),
    ...                Annotation(None, 13, 16, None, None)]
    >>> sampler1 = make_sampler(3, len(text), flanking=False)
    >>> len(sampler1(0, annotations)) == 1
    True
    >>> len(sampler1(2, annotations)) == 3
    True
    >>> extractor(sampler1(0, annotations)[0]) == text[0:10]
    True
    >>> make_sampler(3, 8, flanking=False)(0, annotations)
    []
    >>> len(make_sampler(3, 8, flanking=False)(2, annotations)) == 2
    True
    >>> len(make_sampler(3, 7, flanking=False)(2, annotations)) == 1
    True
    >>> len(make_sampler(3, 6, flanking=False)(2, annotations)) == 0
    True
    """
    # TODO although flanking sampling is implemented, the feautre is
    # TODO deliberately disabled, because `sample_windows` (see below)
    # TODO doesn't handle it properly, yet
    if flanking:
        raise NotImplemented("`flanking` is deliberately disabled")

    def sampler(target: int, annotations: List[Annotation]) \
            -> List[List[Annotation]]:
        windows = slide(target, width, len(annotations), flanking)
        samples = [annotations[first:last] for first, last in windows]
        lens = [annotations[last-1].end - annotations[first].start
                for first, last in windows]
        return [sample for sample, length in zip(samples, lens)
                if length <= maxlen]

    return sampler


def sample_windows(targets: List[int], annotations: List[Annotation],
                   sampler: Sampler) \
        -> Tuple[List[List[Annotation]], List[Annotation]]:
    """
    Sample context windows around positive tokens.
    :return: (list[sampled windows], list[failed target words]);
    failed target words – positive words with no samples of length <= `maxlen`
    """
    samples = [sampler(i, annotations) for i in targets]
    # TODO flanking=True breaks this check; see make_sampler
    failed_targets = [annotations[i] for i, samples in zip(targets, samples)
                      if not samples]
    return list(chain.from_iterable(samples)), failed_targets


def sample_targets(positive_classes: Union[Set[str], Mapping[str, int]],
                   annotations: List[Annotation], nonpos: int) -> List[int]:
    """
    :param positive_classes:
    :param annotations:
    :param nonpos: the maximum number of nonpositive targets to sample
    :return:
    """
    indices = np.arange(len(annotations))
    mask = np.array([anno.cls in positive_classes for anno in annotations])
    positive = indices[mask]
    other = indices[~positive]
    nonpos_sample = np.random.choice(
        other, nonpos if nonpos <= len(other) else len(other), False)
    return list(positive) + list(nonpos_sample)


def encode_text(text: str, sample: List[Annotation], dtype=np.int32) \
        -> np.ndarray:
    if not issubclass(dtype, Integral):
        raise ValueError("`dtype` must be integral")
    start, end = sample[0].start, sample[-1].end
    length = end - start
    encoded = np.fromiter(map(ord, text[start:end]), dtype, length)
    encoded[encoded > (MAXCHAR - 1)] = MAXCHAR
    return encoded


def encode_classes(mapping: Mapping[str, int], sample: List[Annotation],
                   dtype=np.int32) \
        -> np.array:
    if not issubclass(dtype, Integral):
        raise ValueError("`dtype` must be integral")
    try:
        offset = sample[0].start
        length = sample[-1].end - offset
        encoded = np.zeros(length, dtype=dtype)
        for _, start, end, _, cls in sample:
            encoded[start-offset:end-offset] = mapping[cls]
        return encoded
    except KeyError as err:
        raise ValueError("Missing a key in the mapping: {}".format(err))


def join(arrays: List[np.ndarray], dtype=np.int32) \
        -> Tuple[np.ndarray, np.ndarray]:
    """
    Join 1D arrays. The function uses zero-padding to bring all arrays to the
    same length. The dtypes will be coerced to `dtype`
    :return: (joined and padded arrays, boolean array masks); masks are
    positive, i.e. padded regions are False
    """
    if not issubclass(dtype, Integral):
        raise ValueError("`dtype` must be integral")

    ndim = set(arr.ndim for arr in arrays)
    if ndim != {1}:
        raise ValueError("`arrays` must be a nonempty list of 1D numpy arrays")
    maxlen = max(map(len, arrays))
    joined = np.zeros((len(arrays), maxlen), dtype=dtype)
    masks = np.zeros((len(arrays), maxlen), dtype=bool)
    for i, arr in enumerate(arrays):
        joined[i, :len(arr)] = arr
        masks[i, :len(arr)] = True
    return joined, masks


def one_hot(array: np.ndarray) -> np.ndarray:
    """
    One-hot encode an integer array; the output inherits the array's dtype.
    """
    # TODO return check
    # if not issubclass(array.dtype, Integral):
    #     raise ValueError("`array.dtype` must be integral")
    vectors = np.eye(array.max()+1, dtype=array.dtype)
    return vectors[array]


def maskfalse(array: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """
    Replace False-masked items with zeros.
    """
    if not np.issubdtype(mask.dtype, np.bool):
        raise ValueError("Masks are supposed to be boolean")
    copy = array.copy()
    copy[~mask] = 0
    return copy


if __name__ == "__main__":
    raise RuntimeError
