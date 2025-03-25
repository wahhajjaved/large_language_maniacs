from __future__ import division

from itertools import cycle

import numpy as np
import matplotlib.pyplot as plt


class PlotLoss(object):
    def __init__(self, figsize=(8, 5), title=None, update_every=5):
        self.figsize = figsize
        self.title = title
        self.update_every = update_every
        self._fig_is_init = False
        plt.ion()

    def _init_fig(self, nn, train_loss, valid_loss):
        fig, ax = plt.subplots(figsize=self.figsize)

        plt.xlabel("epochs")
        plt.ylabel("loss function")
        plt.grid()

        # fixed scale for axes
        max_epochs = nn.get_params()['max_epochs']
        plt.xlim([0.5, max_epochs + 0.5])
        plt.ylim([0, 1.2 * max(max(train_loss), max(valid_loss))])

        if self.title:
            plt.title(self.title)
        else:
            plt.title(str(nn).split('(')[0])
        return fig, ax

    def __call__(self, nn, train_history):
        train_loss = [info['train_loss'] for info in train_history]
        valid_loss = [info['valid_loss'] for info in train_history]

        n_epochs = len(train_loss)
        if n_epochs % self.update_every != 0:
            return

        if not self._fig_is_init:
            fig, ax = self._init_fig(nn, train_loss, valid_loss)

        # Plot train and validation loss curves
        x = range(1, n_epochs + 1)
        plt.plot(x, train_loss, color='b', label='train')
        plt.plot(x, valid_loss, color='r', label='valid')

        # Place a marker whenever there was a new best valid loss:
        for i in range(n_epochs):
            if i == 0:
                continue
            if valid_loss[i] < min(valid_loss[:i]):
                plt.plot([i + 1], [valid_loss[i]],
                         c='k', ms=8, marker='x')

        if not self._fig_is_init:
            plt.legend()
            self._fig_is_init = True
        plt.pause(0.0001)


class PlotWeights(object):
    def __init__(self, update_every=1, img_x=None, img_y=None,
                 nrows=5, ncols=5, figsize=(8, 8), vis_layer=None,
                 nchannel=1):
        self.update_every = update_every
        self.img_x = img_x
        self.img_y = img_y
        self.nrows = nrows
        self.ncols = ncols
        self.figsize = figsize
        self.vis_layer = vis_layer
        self.nchannel = nchannel
        plt.ion()
        self._fig_is_init = False
        self._num_vis_layer = None

    def _init_fig(self, arr):
        # determine image dimensions
        if arr.ndim == 2:
            # flat image x num_units
            flat_img, num_units = arr.shape
            if (self.img_x is None) or (self.img_y is None):
                self.img_x, self.img_y = self._get_flat_img_dim(flat_img)
        elif arr.ndim == 4:
            # bc01 image
            num_units = arr.shape[0]
            if self.img_x is not None:
                assert self.img_x == arr.shape[2]
            if self.img_y is not None:
                assert self.img_y == arr.shape[3]
            __, __, self.img_x, self.img_y = arr.shape

        # validate number of units
        if self.nrows * self.ncols > num_units:
            raise ValueError(
                "Cannot display {}x{} figures with only {} units.".format(
                    self.nrows, self.ncols, num_units
                )
            )

        # initialize figure
        fig, axes = plt.subplots(nrows=self.nrows, ncols=self.ncols,
                                 figsize=self.figsize)
        plt.xlabel("")
        plt.ylabel("")
        for i in range(self.nrows):
            for j in range(self.ncols):
                # remove ticks
                axes[i][j].set_xticks([])
                axes[i][j].set_yticks([])

        fig.subplots_adjust(
            left=0, right=1, bottom=0, top=1, hspace=0.05, wspace=0.05)
        self.fig = fig
        self.axes = axes
        return self

    def _get_flat_img_dim(self, flat_img):
        # determine dimensions of flat image
        if (self.img_x is None) and (self.img_y is None):
            # if dimensions not indicated, guess quadratic image
            img_x = int(np.sqrt(flat_img))
            img_y = img_x
        elif (self.img_x is None) and (self.img_y is not None):
            img_y = self.img_y
            img_x = flat_img // img_y
        elif (self.img_x is not None) and (self.img_y is None):
            img_x = self.img_x
            img_y = flat_img // img_x
        return img_x, img_y

    def _get_vis_layer(self, nn):
        """ Determine which layer to visualize.
        """
        if self.vis_layer is None:
            return 1  # per default, visualize layer 1

        layer_names, __ = zip(*nn.layers)
        if self.vis_layer not in layer_names:
            raise ValueError(
                "There is no layer called {} to be visualized".format(
                    self.vis_layer
                )
            )
        return layer_names.index(self.vis_layer)


    def __call__(self, nn, train_history):
        if len(train_history) % self.update_every != 0:
            return

        if self._num_vis_layer is None:
            self._num_vis_layer = self._get_vis_layer(nn)
        arr = nn.get_all_params()[self._num_vis_layer].get_value()

        if not self._fig_is_init:
            self._init_fig(arr)
            self._fig_is_init = True
        axes = self.axes
        for i in range(self.nrows):
            for j in range(self.ncols):
                if arr.ndim == 2:  # flat image
                    img = arr[:, i + self.nrows * j].reshape(self.img_y,
                                                             self.img_x)
                else:  # bc01 image:
                    img = arr[i + self.nrows * j][self.nchannel]
                axes[i][j].imshow(img, interpolation='nearest',
                                  cmap=plt.get_cmap('gray'))

        plt.pause(0.0001)


class PlotWeightChanges(object):
    def __init__(self, figsize=(8, 5), title=None, update_every=5):
        self.figsize = figsize
        self.title = title
        self.update_every = update_every
        self._fig_is_init = False
        self._weight_history = []
        plt.ion()

    def _init_fig(self, nn):
        fig, ax = plt.subplots(figsize=self.figsize)

        ax.set_xlabel("epochs")
        ax.set_ylabel("normalized absolute change in weights")
        plt.grid()

        # fixed scale for x-axis
        max_epochs = nn.get_params()['max_epochs']
        ax.set_xlim([1.5, max_epochs + 0.5])
        ax.set_ylim([0, 1.2])

        # don't take input layer
        self._layer_names = zip(*nn.layers)[0][1:]

        if self.title:
            ax.set_title(self.title)
        else:
            ax.set_title(str(nn).split('(')[0])
        return fig, ax

    def _get_weights(self, nn):
        # every other is weight (others are biases)
        weights = [l.get_value() for l in nn.get_all_params()[1::2]]
        return weights

    def __call__(self, nn, train_history):
        n_epochs = len(train_history)
        current_weights = self._get_weights(nn)
        if n_epochs == 1:
            self._last_weights = current_weights
            return
        self._weight_history.append(
            [np.abs(lw - cw).sum() for lw, cw in
             zip(self._last_weights, current_weights)]
        )
        self._last_weights = current_weights
        if n_epochs % self.update_every != 0:
            return

        if not self._fig_is_init:
            fig, ax = self._init_fig(nn)
            self._fig_is_init = True

        # Plot normalized absolute weight changes
        weight_history = self._weight_history
        w0 = weight_history[0]
        x = range(2, n_epochs + 1)
        Y = np.array(weight_history) / w0
        colors = cycle(['r', 'g', 'b', 'c', 'm', 'y', 'k'])
        for y, color in zip(zip(*Y), colors):
            plt.plot(x, y, '.-', c=color)
        plt.legend(self._layer_names, loc='best')

        plt.pause(0.0001)
