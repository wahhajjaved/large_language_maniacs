#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# CREATED:2015-03-03 21:29:49 by Brian McFee <brian.mcfee@nyu.edu>
'''Additive background noise'''

import pysoundfile as psf
import librosa
import numpy as np
import os
import six

from ..base import BaseTransformer


def sample_clip(filename, n_samples, sr, mono=True):
    '''Sample a fragment of audio from a file.

    This uses pysoundfile to efficiently seek without
    loading the entire stream.

    Parameters
    ----------
    filename : str
        Path to the input file

    n_samples : int > 0
        The number of samples to load

    sr : int > 0
        The target sampling rate

    mono : bool
        Ensure monophonic audio

    Returns
    -------
    y : np.ndarray [shape=(n_samples,)]
        A fragment of audio sampled randomly from `filename`

    Raises
    ------
    ValueError
        If the source file is shorter than the requested length

    '''

    with psf.SoundFile(filename, mode='r') as soundf:

        n_target = int(np.ceil(n_samples * soundf.samplerate / sr))

        # Draw a random clip
        start = np.random.randint(0, len(soundf) - n_target)

        soundf.seek(start)

        y = soundf.read(n_target).T

    if mono:
        y = librosa.to_mono(y)

    # Resample to initial sr
    y = librosa.resample(y, soundf.samplerate, sr)

    # Clip to the target length exactly
    y = librosa.util.fix_length(y, n_samples)

    return y


class BackgroundNoise(BaseTransformer):
    '''Additive background noise deformations'''

    def __init__(self, n_samples, files, weight_min, weight_max):
        '''Additive background noise deformations

        Parameters
        ----------
        n_samples : int > 0
            The number of samples to generate with each noise source

        files : str or list of str
            Path to audio file(s) on disk containing background signals

        weight_min : float in (0.0, 1.0)
        weight_max : float in (0.0, 1.0)
            The minimum and maximum weight to combine input signals

            `y_out = (1 - weight) * y + weight * y_noise`
        '''

        if n_samples <= 0:
            raise ValueError('n_samples must be strictly positive')

        if not 0 < weight_min < weight_max < 1.0:
            raise ValueError('weights must be in the range (0.0, 1.0)')

        if isinstance(files, six.string_types):
            files = [files]

        for fname in files:
            if not os.path.exists(fname):
                raise RuntimeError('file not found: {}'.format(fname))

        BaseTransformer.__init__(self)

        self.n_samples = n_samples
        self.files = files
        self.weight_min = weight_min
        self.weight_max = weight_max

    def get_state(self, jam):
        '''Build the noise state'''

        state = BaseTransformer.get_state(self, jam)

        if not len(self._state):
            state['files'] = self.files
            state['index'] = 0
        else:
            state.update(self._state)
            state['index'] += 1

        state['weight'] = np.random.uniform(low=self.weight_min,
                                            high=self.weight_max,
                                            size=None)
        return state

    def audio(self, mudabox):
        '''Deform the audio'''

        # State needs to specify:
        #   filename
        #   weight

        idx = self._state['index']
        weight = self._state['weight']

        fname = self.files[idx % len(self.files)]

        noise = sample_clip(fname, len(mudabox['y']), mudabox['sr'],
                            mono=mudabox['y'].ndim == 1)

        # Normalize the data
        mudabox['y'] = librosa.util.normalize(mudabox['y'])
        noise = librosa.util.normalize(noise)

        mudabox['y'] = (1.0 - weight) * mudabox['y'] + weight * noise
