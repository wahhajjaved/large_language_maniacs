from typing import Tuple, Text, Sequence, Optional
from itertools import groupby, chain
import operator as op

import numpy as np

from sciner.intervals import Interval, span, extract
from sciner.util import oldmap

ProcessedSample = Tuple[int, Text, Sequence[Interval], Sequence[Text],
                        Optional[np.ndarray]]


def annotate_sample(nlabels: int, annotation: np.ndarray,
                    sample: Sequence[Interval], dtype=np.int32) -> np.ndarray:
    # TODO update docs
    # TODO pass spans instead of samples
    """
    :param sample: a sequence of Intervals
    :param dtype: output data type; it must be an integral numpy dtype
    :return: encoded annotation
    """
    if not np.issubdtype(dtype, np.int):
        raise ValueError("`dtype` must be integral")
    span_ = span(sample)
    if span_ is None:
        raise ValueError("The sample is empty")
    if span_.stop > len(annotation):
        raise ValueError("The annotation doesn't fully cover the sample")
    tk_annotations = extract(annotation, sample)
    encoded_token_anno = np.zeros((len(sample), nlabels), dtype=np.int32)
    for i, tk_anno in enumerate(tk_annotations):
        encoded_token_anno[i, tk_anno] = 1
    return encoded_token_anno


def annotate_borders(annotation: np.ndarray) -> np.ndarray:
    if annotation.ndim != 1 or np.issubdtype(annotation.dtype, np.int):
        raise ValueError("`annotation` must be a 1D integer array")

    getpos = op.itemgetter(0)
    getlabel = op.itemgetter(1)
    runs = (oldmap(getpos, run)
            for label, run in groupby(enumerate(annotation), getlabel)
            if label)
    borders = np.zeros(len(annotation), dtype=annotation.dtype)
    for indices in runs:
        if len(indices) == 1:
            borders[indices[0]] = 3
        else:
            first, last = indices[0], indices[-1]
            borders[first] = 1
            borders[last] = 2
    return borders


if __name__ == "__main__":
    raise RuntimeError
