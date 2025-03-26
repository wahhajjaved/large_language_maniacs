# -*- coding: utf-8 -*-

# Copyright (c) 2018 shmilee

'''
Contains plotter, plotemplate base class.
'''

import os
import numpy

from ..glogger import getGLogger

__all__ = ['BasePlotter', 'BasePloTemplate']
log = getGLogger('P')


class BasePlotter(object):
    '''
    Plot data, create figures.

    Attributes
    ----------
    name: str
        plotter name
    style_available: list of str
        available styles for this plotter
    style: list of str
        list of default styles, valid elements can be in *style_available*
    figures: list
        list of figure nums(labels) created by this plotter
    example_axes: str
        example structure of an axes

    Notes
    -----
    The plotter instance is callable.
    instance() is equivalent to instance.create_figure().
    '''
    __slots__ = ['name', 'example_axes', '_style', '_figureslib']
    style_available = []

    def __init__(self, name, style=[], example_axes=None):
        self.name = name
        self.style = style
        self.example_axes = example_axes
        self._figureslib = {}

    def _get_style(self):
        return self._style

    def _set_style(self, style):
        self._style = []
        for sty in style:
            if self._check_style(sty):
                self._style.append(sty)
            else:
                log.warn("Ignore style '%s': %s" % (sty, 'not available'))

    style = property(_get_style, _set_style)

    def _check_style(self, sty):
        '''Check single style *sty* available or not.'''
        # return sty in self.style_available
        raise NotImplementedError()

    def check_style(self, style):
        '''
        Check the *style* available or not.
        Accept a list. Return available style list.
        '''
        return [sty for sty in style if self._check_style(sty)]

    def _filter_style(self, sty):
        '''Change *sty* str to absolute path.'''
        raise NotImplementedError()

    def filter_style(self, style):
        '''
        Filter the *style* list before use it.
        If the str starts with 'gdpy3-', change it to absolute path.
        Accept a list. Return a list.
        '''
        newstyle = []
        for sty in style:
            if isinstance(sty, str) and sty.startswith('gdpy3-'):
                newstyle.append(self._filter_style(sty))
            else:
                newstyle.append(sty)
        return newstyle

    def _param_from_style(self, param):
        raise NotImplementedError()

    def param_from_style(self, param):
        '''
        Return *param* value from self.style
        '''
        return self._param_from_style(param)

    @property
    def figures(self):
        return list(self._figureslib.keys())

    def _add_axes(self, fig, data, layout, axstyle):
        '''Add axes to figure.'''
        raise NotImplementedError()

    def add_axes(self, fig, axstructure):
        '''
        Add axes to figure *fig*.

        Parameters
        ----------
        fig: figure object
        axstructure: dict, structure of an axes
        '''
        # simple check
        if not isinstance(axstructure, dict):
            log.error("AxesStructure must be dict. Not %s. Ignore this axes."
                      % type(axstructure))
            return
        check_pass = True
        for k in ('data', 'layout'):
            if k not in axstructure:
                check_pass = False
                log.error("AxesStructure must contain key: '%s'!" % k)
            if not isinstance(axstructure[k], list):
                check_pass = False
                log.error("AxesStructure[%s] must be list. Not %s."
                          % (k, type(axstructure[k])))
        layout = axstructure['layout']
        if not(isinstance(layout, list) and len(layout) == 2):
            check_pass = False
            log.error("AxesStructure['layout'] must have 2 elements.")
        if not check_pass:
            log.error("Ignore this axes.")
            return
        # check axstyle
        axstyle = []
        if 'axstyle' in axstructure:
            if isinstance(axstructure['axstyle'], list):
                axstyle = self.check_style(axstructure['axstyle'])
            else:
                log.error("AxesStructure['axstyle'] must be list. Not %s. "
                          % type(axstructure['axstyle'])
                          + "Ignore 'axstyle' setting!")
        log.ddebug("Axes Style: %s" % str(axstyle))
        return self._add_axes(fig, axstructure['data'], layout, axstyle)

    def _create_figure(self, num, axesstructures, figstyle):
        '''Create a figure object.'''
        raise NotImplementedError()

    def create_figure(self, num, *axesstructures, add_style=None, replace=True):
        '''
        Use *axesstructures* to create a figure object.

        Parameters
        ----------
        num: integer or string
            figure's number or figlabel, do not use 'all'
        axestructures: list of AxesStructure dict
        add_style: list of style, default: none
            more style for this figure
        replace: bool
            if figure *num* was created, replace it or just return it

        Notes
        -----
        1. Value of *axesstructures* is a list of `AxesStructure`.
           Each `AxesStructure` is a dict which has 3 keys:
           'data', 'layout' and 'axstyle'. 'axstyle' is optional.
        2. Value of 'data' is a list of plot items. items[0] is an order
           number. items[1] is a name of plot method. It can be any plot
           function supported by the backend. items[2] is a tuple of args
           for plot function. items[3] is a dict of kwargs for plot function.
        3. Value of 'layout' is a list of two elements. layout[0] is
           position. layout[1] is a dict of kwargs.
        4. Value of 'axstyle' is a list of style. The axstyle will only
           affect this axes except others.
        '''
        if num in self._figureslib:
            if replace:
                log.warn("Figure %s was created. Closing it!" % num)
                self.close_figure(num)
            else:
                return self.get_figure(num)
        figstyle = self.style.copy()
        if add_style and isinstance(add_style, list):
            figstyle.extend(self.check_style(add_style))
        log.ddebug("Figure Style: %s" % str(figstyle))
        figure = self._create_figure(num, axesstructures, figstyle)
        if figure:
            self._figureslib[num] = figure
            return figure
        else:
            return None

    def __call__(self, *args, **kwargs):
        '''callable'''
        return self.create_figure(*args, **kwargs)

    def get_figure(self, num):
        '''
        Return figure *num* if already created.
        '''
        if num in self._figureslib:
            return self._figureslib[num]
        else:
            return None

    def _show_figure(self, fig):
        '''Display figure object *fig*.'''
        raise NotImplementedError()

    def show_figure(self, num):
        '''
        Display figure *num* if already created.
        '''
        if num in self._figureslib:
            return self._show_figure(self._figureslib[num])
        else:
            log.error("Figure %s is not created!" % num)

    def _close_figure(self, fig):
        '''Close figure object *fig*.'''
        raise NotImplementedError()

    def close_figure(self, num):
        '''
        Close figure *num* if already created.
        ``close_figure('all')`` closes all the figure
        '''
        if num == 'all':
            for n in tuple(self._figureslib.keys()):
                fig = self._figureslib.pop(n, None)
                if fig:
                    self._close_figure(fig)
                del fig
        elif num in self._figureslib:
            fig = self._figureslib.pop(num, None)
            if fig:
                self._close_figure(fig)
            del fig

    def _save_figure(self, fig, fpath, **kwargs):
        '''Save figure object *fig*.'''
        raise NotImplementedError()

    def save_figure(self, num, fpath, **kwargs):
        '''
        Save figure *num* to *fpath* if already created.
        '''
        if num in self._figureslib:
            log.info("Save figure to %s ..." % fpath)
            self._save_figure(self._figureslib[num], fpath, **kwargs)
        else:
            log.error("Figure %s is not created!" % num)


class BasePloTemplate(object):
    '''
    Some plot templates(methods)
        Use *results* to get a list of axesstructure and add_style.

    Attributes
    ----------
    template_available: tuple
        all available templates
    '''
    __slots__ = []
    template_available = [
        'template_sharex_twinx_axstructs',
        'template_pcolor_axstructs',
    ]

    def template_sharex_twinx_axstructs(self, results):
        '''
        Template
        --------
        .. code::

                   title
                 +--------+
          ylabel | axes 1 | ylabel
                 +--------+
          ylabel | axes 2 | ylabel
                 +--------+
                   xlabel

        Parameters
        ----------
        results['X']: list or numpy.ndarray, required
            1 dimension array
        results['YINFO']: list of dict, required
            all info for the axes
        results['hspace']: float, optional
            height space between subplots, default 0.02
        results['title']: str, optional
            default None
        results['xlabel']: str, optional
            default None
        results['xlim']: (`left`, `right`), optional
            default [min(X), max(X)]
        results['ylabel_rotation']: str or int, optional
            default 'vertical'

        Notes
        -----
        Form of *YINFO*.

        .. code:: python

            yinfo = [{
                # axes 1
                'left': [(ydata1, label1), (ydata2, label2)], # required
                'right': [(ydata3, label3)], # required
                'llegend': dict(loc='upper left'), # optional
                'rlegend': dict(loc='upper right'), # optional
                'lylabel': 'left ylabel', # optional
                'rylabel': 'right ylabel', # optional
            }, {
                # axes 2
                'left': [([1,...,9], 'line')], 'right': [],
                'lylabel': 'Y2',
            }]

        yinfo[0]['left'][0]: len(ydata1) == len(X)
        yinfo[1]['right']: can be empty list
        yinfo[0]['llegend']: optional kwargs for legend
        '''
        # check
        if not ('X' in results and 'YINFO' in results):
            log.error("`X` and `YINFO` are required!")
            return [], []
        if isinstance(results['X'], (list, range, numpy.ndarray)):
            X = results['X']
        else:
            log.error("`X` must be array!")
            return [], []
        if not isinstance(results['YINFO'], list):
            log.error("`YINFO` array must be list!")
            return [], []
        for i, ax in enumerate(results['YINFO'], 1):
            if not (isinstance(ax, dict) and 'left' in ax and 'right' in ax):
                log.error("Info of axes %d must be dict!"
                          "Key 'left', 'right' must in it!" % i)
                return [], []
            for lr in ['left', 'right']:
                for j, line in enumerate(ax[lr], 1):
                    if not isinstance(line[0], (list, range, numpy.ndarray)):
                        log.error(
                            "Info of line %d in axes %d %s must be array!"
                            % (j, i, lr))
                        return [], []
                    if len(line[0]) != len(X):
                        log.error(
                            "Invalid array length of line %d in axes %d %s!"
                            % (j, i, lr))
                        return [], []
        YINFO = results['YINFO']
        hspace = float(results['hspace']) if 'hspace' in results else 0.02
        title = str(results['title']) if 'title' in results else None
        xlabel = str(results['xlabel']) if 'xlabel' in results else None
        if 'xlim' in results and len(results['xlim']) == 2:
            xlim = results['xlim']
        else:
            xlim = [numpy.min(X), numpy.max(X)]
        if ('ylabel_rotation' in results
                and isinstance(results['ylabel_rotation'], (int, str))):
            ylabel_rotation = results['ylabel_rotation']
        else:
            ylabel_rotation = 'vertical'
        return self._template_sharex_twinx_axstructs(
            X, YINFO,
            hspace, title, xlabel, xlim, ylabel_rotation)

    @staticmethod
    def _template_sharex_twinx_axstructs(
            X, YINFO,
            hspace, title, xlabel, xlim, ylabel_rotation):
        '''
        For :meth:`template_sharex_twinx_axstructs`.
        Return [*AxStructs], add_style
        '''
        raise NotImplementedError()

    def template_pcolor_axstructs(self, results):
        '''
        Template
        --------
        .. code::

                   title
                 +--------+ +-+
          ylabel | pcolor | |-|colorbar
                 +--------+ +-+
                   xlabel

        Parameters
        ----------
        results['X']: 1 or 2 dimension numpy.ndarray, required
        results['Y']: 1 or 2 dimension numpy.ndarray, required
        results['Z']: 2 dimension numpy.ndarray, required
            (len(Y), len(X)) == Z.shape or (X.shape == Y.shape == Z.shape)
        results['plot_method']: str, optional
            'pcolor', 'pcolormesh', 'contourf' or 'plot_surface'
            default 'pcolor'
        results['plot_method_args']: list, optional
            args for *plot_method*, like levels for 'contourf'
        results['plot_method_kwargs']: dict, optional
            kwargs for *plot_method*,
            like cmap for 'plot_surface', default in style
        results['title']: str, optional
        results['xlabel']: str, optional
        results['ylabel']: str, optional
        results['colorbar']: bool, optional
            add colorbar or not, default True
        results['grid_alpha']: float, optional
            transparency of grid, use this when 'grid.alpha' has no effect
        results['plot_surface_shadow']: list, optional
            add contourf in a surface plot, ['x', 'y', 'z'], default []
        '''
        if not ('X' in results
                and 'Y' in results and 'Z' in results):
            log.error("`X`, 'Y' and `Z` are required!")
            return [], []
        for _x in ['X', 'Y', 'Z']:
            if not isinstance(results[_x], numpy.ndarray):
                log.error("`%s` array must be numpy.ndarray!" % _x)
                return [], []
        X = results['X']
        Y = results['Y']
        Z = results['Z']
        if len(X.shape) == 1 and len(Y.shape) == 1:
            # X, Y: 1 dimension
            if (len(Y), len(X)) != Z.shape:
                log.error("Invalid `X`, `Y` length or `Z` shape!")
                return [], []
            X, Y = np.meshgrid(X, Y)
        elif len(X.shape) == 2 and len(Y.shape) == 2:
            # X, Y: 2 dimension
            if not (X.shape == Y.shape == Z.shape):
                log.error("Invalid `X`, `Y` or `Z` shape!")
                return [], []
        else:
            log.error("Invalid `X`, `Y` dimension!")
            return [], []
        if ('plot_method' in results
                and results['plot_method'] in (
                    'pcolor', 'pcolormesh', 'contourf', 'plot_surface')):
            plot_method = results['plot_method']
        else:
            plot_method = 'pcolor'
        if ('plot_method_args' in results
                and isinstance(results['plot_method_args'], list)):
            plot_method_args = results['plot_method_args']
        else:
            plot_method_args = []
        if ('plot_method_kwargs' in results
                and isinstance(results['plot_method_kwargs'], dict)):
            plot_method_kwargs = results['plot_method_kwargs']
        else:
            plot_method_kwargs = {}
        if 'cmap' not in plot_method_kwargs:
            plot_method_kwargs['cmap'] = self.param_from_style('image.cmap')
        title = str(results['title']) if 'title' in results else None
        xlabel = str(results['xlabel']) if 'xlabel' in results else None
        ylabel = str(results['ylabel']) if 'ylabel' in results else None
        colorbar = bool(results['colorbar'] if 'colorbar' in results else 1)
        if 'grid_alpha' in results:
            grid_alpha = float(results['grid_alpha'])
        else:
            grid_alpha = None
        if ('plot_surface_shadow' in results
                and isinstance(results['plot_surface_shadow'], list)):
            _sl, _sl_val = results['plot_surface_shadow'], ['x', 'y', 'z']
            _sl = filter(lambda x: True if x in _sl_val else False, _sl)
            plot_surface_shadow = list(_sl)
        else:
            plot_surface_shadow = []
        log.ddebug("Some template pcolor parameters: %s" % [
            plot_method, plot_method_args, plot_method_kwargs,
            colorbar, grid_alpha, plot_surface_shadow])
        return self._template_pcolor_axstructs(
            X, Y, Z, plot_method, plot_method_args, plot_method_kwargs,
            title, xlabel, ylabel, colorbar, grid_alpha, plot_surface_shadow)

    @staticmethod
    def _template_pcolor_axstructs(
            X, Y, Z, plot_method, plot_method_args, plot_method_kwargs,
            title, xlabel, ylabel, colorbar, grid_alpha, plot_surface_shadow):
        '''For :meth:`template_pcolor_axstructs`.'''
        raise NotImplementedError()
