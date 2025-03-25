from itertools import product, groupby
from collections import OrderedDict

import numpy as np
from mpl_toolkits.mplot3d import Axes3D
import matplotlib
from matplotlib import pyplot as plt
from matplotlib import gridspec, animation

import param
from ..core import NdMapping, UniformNdMapping, ViewableElement, HoloMap, \
    AdjointLayout, NdLayout, AxisLayout, LayoutTree, Element
from ..core.options import Options, OptionTree
from ..core.traversal import unique_dimkeys, uniform
from ..core.util import find_minmax, valid_identifier
from ..element.raster import Raster


class Plot(param.Parameterized):
    """
    A Plot object returns either a matplotlib figure object (when
    called or indexed) or a matplotlib animation object as
    appropriate. Plots take element objects such as Matrix,
    Contours or Points as inputs and plots them in the
    appropriate format. As views may vary over time, all plots support
    animation via the anim() method.
    """

    aspect = param.Parameter(default=None, doc="""
        The aspect ratio mode of the plot. By default, a plot may
        select its own appropriate aspect ratio but sometimes it may
        be necessary to force a square aspect ratio (e.g. to display
        the plot as an element of a grid). The modes 'auto' and
        'equal' correspond to the axis modes of the same name in
        matplotlib, a numeric value may also be passed.""")

    figure_bounds = param.NumericTuple(default=(0.15, 0.15, 0.85, 0.85),
                                       doc="""
        The bounds of the figure as a 4-tuple of the form
        (left, bottom, right, top), defining the size of the border
        around the subplots.""")

    finalize_hooks = param.HookList(default=[], doc="""
        Optional list of hooks called when finalizing an axis.
        The hook is passed the full set of plot handles and the
        displayed object.""")

    normalize = param.Boolean(default=True, doc="""
        Whether to compute ranges across all Elements at this level
        of plotting. Allows selecting normalization at different levels
        for nested data containers.""")

    projection = param.ObjectSelector(default=None,
                                      objects=['3d', 'polar', None], doc="""
        The projection of the plot axis, default of None is equivalent to
        2D plot, 3D and polar plots are also supported.""")

    show_frame = param.Boolean(default=True, doc="""
        Whether or not to show a complete frame around the plot.""")

    show_title = param.Boolean(default=True, doc="""
        Whether to display the plot title.""")

    size = param.NumericTuple(default=(4, 4), doc="""
        The matplotlib figure size in inches.""")

    # A list of matplotlib keyword arguments that may be supplied via a
    # style options object. Each subclass should override this
    # parameter to list every option that works correctly.
    style_opts = []

    # A mapping from ViewableElement types to their corresponding plot types
    defaults = {}

    # A mapping from ViewableElement types to their corresponding side plot types
    sideplots = {}

    # Once register_options is called, this OptionTree is populated
    options = OptionTree(groups={'plot':  Options(),
                                 'style': Options(),
                                 'norm':  Options()})

    # A dictionary of custom OptionTree by custom id
    custom_options = {}


    def __init__(self, figure=None, axis=None, dimensions=None,
                 subplots=None, uniform=True, keys=None, subplot=None, **params):
        self.subplots = subplots
        self.subplot = figure is not None or subplot
        self.dimensions = dimensions
        self.keys = keys
        self.uniform = uniform

        self._create_fig = True
        self.drawn = False
        # List of handles to matplotlib objects for animation update
        self.handles = {} if figure is None else {'fig': figure}
        super(Plot, self).__init__(**params)
        self.handles['axis'] = self._init_axis(axis)


    @classmethod
    def lookup_options(cls, obj, group):
        if obj.id is None:
            return cls.options.closest(obj, group)
        elif obj.id in cls.custom_options:
            return cls.custom_options[obj.id].closest(obj, group)
        else:
            raise KeyError("No custom settings defined for object with id %d" % obj.id)


    def compute_ranges(self, obj, key, ranges):
        """
        Given an object, a specific key and the normalization options
        this method will find the specified normalization options on
        the appropriate OptionTree, group the elements according to
        the selected normalization option (i.e. either per frame or
        over the whole animation) and finally compute the dimension
        ranges in each group. The new set of ranges is returned.
        """
        if obj is None or not self.normalize:
            return OrderedDict()
        # Get inherited ranges
        ranges = {} if ranges is None else dict(ranges)

        # Get element identifiers from current object and resolve
        # with selected normalization options
        norm_opts = self._get_norm_opts(obj)

        # Traverse displayed object if normalization applies
        # at this level, and ranges for the group have not
        # been supplied from a composite plot
        return_fn = lambda x: x if isinstance(x, Element) else None
        for group, (groupwise, mapwise) in norm_opts.items():
            if group in ranges:
                continue # Skip if ranges are already computed
            elif mapwise: # Traverse to get all elements
                elements = obj.traverse(return_fn, [group])
            elif key is not None: # Traverse to get elements for each frame
                elements = self._get_frame(key).traverse(return_fn, [group])
            if groupwise: # Compute new ranges
                self._compute_group_range(group, elements, ranges)
        return ranges


    def _get_norm_opts(self, obj):
        """
        Gets the normalization options for a LabelledData object by
        traversing the object for to find elements and their ids.
        The id is then used to select the appropriate OptionsTree,
        accumulating the normalization options into a dictionary.
        Returns a dictionary of normalization options for each
        element in the tree.
        """
        norm_opts = {}

        # Get all elements' type.value.label specs and ids
        type_val_fn = lambda x: (x.id, (type(x).__name__, valid_identifier(x.value),
                                        valid_identifier(x.label))) \
            if isinstance(x, Element) else None
        element_specs = {(idspec[0], idspec[1]) for idspec in obj.traverse(type_val_fn)
                         if idspec is not None}

        # Group elements specs by ID and override normalization
        # options sequentially
        id_groups = sorted(groupby(element_specs, lambda x: x[0]))
        for gid, element_spec_group in id_groups:
            group_specs = [el for _, el in element_spec_group]
            optstree = self.custom_options.get(gid, Plot.options)
            # Get the normalization options for the current id
            # and match against customizable elements
            for opts in optstree:
                path = tuple(opts.path.split('.')[1:])
                applies = any(path == spec[:i] for spec in group_specs
                              for i in range(1, 4))
                if applies and 'norm' in opts.groups:
                    nopts = opts['norm'].options
                    if 'groupwise' in nopts or 'mapwise' in nopts:
                        norm_opts.update({path: (opts['norm'].options.get('groupwise', True),
                                                 opts['norm'].options.get('mapwise', True))})
        element_specs = [spec for eid, spec in element_specs]
        norm_opts.update({spec: (True, True) for spec in element_specs
                          if not any(spec[:i] in norm_opts.keys() for i in range(1, 4))})
        return norm_opts


    @staticmethod
    def _compute_group_range(group, elements, ranges):
        # Iterate over all elements in a normalization group
        # and accumulate their ranges into the supplied dictionary.
        elements = [el for el in elements if el is not None]
        for el in elements:
            for dim in el.dimensions(label=True):
                dim_range = el.range(dim)
                if group not in ranges: ranges[group] = OrderedDict()
                if dim in ranges[group]:
                    ranges[group][dim] = find_minmax(ranges[group][dim], dim_range)
                else:
                    ranges[group][dim] = dim_range


    def _get_frame(self, key):
        """
        Required on each Plot type to get the data corresponding
        just to the current frame out from the object.
        """
        pass


    @classmethod
    def register_options(cls):
        path_items = {}
        for view_class, plot in Plot.defaults.items():
            name = view_class.__name__
            plot_opts = [k for k in plot.params().keys() if k not in ['name']]
            style_opts = plot.style_opts
            opt_groups = {'plot': Options(allowed_keywords=plot_opts)}
            if not isinstance(plot, CompositePlot) or hasattr(plot, 'style_opts'):
                opt_groups.update({'style': Options(allowed_keywords=style_opts),
                                   'norm':  Options(mapwise=True, groupwise=True,
                                                    allowed_keywords=['groupwise',
                                                                      'mapwise'])})
            path_items[name] = opt_groups
        cls.options = OptionTree(sorted(path_items.items()),
                                  groups={'style': Options(), 'plot': Options(),
                                          'norm': Options()})


    def _format_title(self, key):
        view = self.map.get(key, None)
        if view is None: return None
        title_format = self.map.get_title(key if isinstance(key, tuple) else (key,), view)
        if title_format is None:
            return None
        return title_format.format(label=view.label, value=view.value,
                                   type=view.__class__.__name__)


    def _finalize_axis(self, key):
        """
        General method to finalize the axis and plot.
        """

        self.drawn = True
        if self.subplot:
            return self.handles['axis']
        else:
            plt.draw()
            fig = self.handles['fig']
            plt.close(fig)
            return fig


    def _init_axis(self, axis):
        """
        Return an axis which may need to be initialized from
        a new figure.
        """
        if not self.subplot and self._create_fig:
            fig = plt.figure()
            self.handles['fig'] = fig
            l, b, r, t = self.figure_bounds
            fig.subplots_adjust(left=l, bottom=b, right=r, top=t)
            fig.set_size_inches(list(self.size))
            axis = fig.add_subplot(111, projection=self.projection)
            axis.set_aspect('auto')

        return axis


    def __getitem__(self, frame):
        """
        Get the matplotlib figure at the given frame number.
        """
        if frame > len(self):
            self.warning("Showing last frame available: %d" % len(self))
        if not self.drawn: self.handles['fig'] = self()
        self.update_frame(self.keys[frame])
        return self.handles['fig']


    def anim(self, start=0, stop=None, fps=30):
        """
        Method to return an Matplotlib animation. The start and stop
        frames may be specified as well as the fps.
        """

        frames = list(range(len(self)))[slice(start, stop, 1)]

        figure = self()
        anim = animation.FuncAnimation(figure, self.update_frame,
                                       frames=self.keys,
                                       interval = 1000.0/fps)
        # Close the figure handle
        plt.close(figure)
        return anim

    def __len__(self):
        """
        Returns the total number of available frames.
        """
        return len(self.keys)


    def __call__(self, ranges=None):
        """
        Return a matplotlib figure.
        """
        raise NotImplementedError


    def update_frame(self, key, ranges=None):
        """
        Updates the current frame of the plot.
        """
        raise NotImplementedError


    def update_handles(self, axis, view, key, ranges=None):
        """
        Should be called by the update_frame class to update
        any handles on the plot.
        """
        pass


class CompositePlot(Plot):
    """
    CompositePlot provides a baseclass for plots coordinate multiple
    subplots to form a Layout.
    """

    def update_frame(self, key):
        ranges = self.compute_ranges(self.layout, key, None)
        for subplot in self.subplots.values():
            subplot.update_frame(key, ranges=ranges)
        axis = self.handles['axis']
        self.update_handles(axis, self.layout, key, ranges)


    def _get_frame(self, key):
        """
        Creates a clone of the Layout with the nth-frame for each
        Element.
        """
        layout_frame = self.layout.clone()
        nthkey_fn = lambda x: zip(tuple(x.name for x in x.key_dimensions),
                                  x.data.keys()[max([key, len(x)-1])])
        for path, item in self.layout.items():
            if self.uniform:
                dim_keys = zip([d.name for d in self.dimensions], key)
            else:
                dim_keys = item.traverse(nthkey_fn, ('HoloMap',))
            if dim_keys:
                layout_frame[path] = item.select(**dict(dim_keys))
            else:
                layout_frame[path] = item
        return layout_frame


    def __len__(self):
        return len(self.keys)



class GridPlot(CompositePlot):
    """
    Plot a group of elements in a grid layout based on a AxisLayout element
    object.
    """

    show_legend = param.Boolean(default=False, doc="""
        Legends add to much clutter in a grid and are disabled by default.""")

    show_title = param.Boolean(default=False)

    def __init__(self, layout, ranges=None, keys=None, dimensions=None, **params):
        if not isinstance(layout, AxisLayout):
            raise Exception("GridPlot only accepts AxisLayout.")
        self.cols, self.rows = layout.shape
        extra_opts = self.lookup_options(layout, 'plot').options
        if not keys or not dimensions:
            dimensions, keys = unique_dimkeys(layout)

        super(GridPlot, self).__init__(keys=keys, dimensions=dimensions,
                                       uniform=uniform(layout),
                                       **dict(extra_opts, **params))
        # Compute ranges layoutwise
        self._layoutspec = gridspec.GridSpec(self.rows, self.cols)
        self.subplots, self.subaxes, self.layout = self._create_subplots(layout, ranges)


    def _create_subplots(self, layout, ranges=None, create_axis=True):
        subplots, subaxes = OrderedDict(), OrderedDict()

        frame_ranges = self.compute_ranges(layout, None, ranges)
        frame_ranges = OrderedDict([(key, self.compute_ranges(layout, key, frame_ranges))
                                    for key in self.keys])
        collapsed_layout = layout.clone(id=layout.id)
        r, c = (0, 0)
        for coord in layout.keys(full_grid=True):
            # Create axes
            if create_axis:
                subax = plt.subplot(self._layoutspec[r, c])
                subax.axis('off')
                subaxes[(r, c)] = subax
            else:
                subax = None

            # Create subplot
            if not isinstance(coord, tuple): coord = (coord,)
            view = layout.data.get(coord, None)
            if view is not None:
                layout_dimvals = dict(AxisLayout=zip(zip(layout.key_dimensions, coord)))
                vtype = view.type if isinstance(view, HoloMap) else view.__class__
                subplot = Plot.defaults[vtype](view, figure=self.handles['fig'], axis=subax,
                                               dimensions=self.dimensions, show_title=False,
                                               subplot=not create_axis, ranges=frame_ranges,
                                               uniform=self.uniform)
                collapsed_layout[coord] = subplot.map
                subplots[(r, c)] = subplot
            if r != self.rows-1:
                r += 1
            else:
                r = 0
                c += 1
        if create_axis:
            self.handles['axis'] = self._layout_axis(layout)
            self._adjust_subplots(self.handles['axis'], subaxes)

        return subplots, subaxes, collapsed_layout


    def __call__(self, ranges=None):
        # Get the extent of the layout elements (not the whole layout)
        subplot_kwargs = dict()
        ranges = self.compute_ranges(self.layout, self.keys[-1], ranges)
        for subplot in self.subplots.values():
            subplot(ranges=ranges, **subplot_kwargs)

        self.drawn = True
        if self.subplot: return self.handles['axis']
        plt.close(self.handles['fig'])
        return self.handles['fig']


    def _format_title(self, key):
        title_format = self.layout.title
        return title_format.format(label=self.layout.label, value=self.layout.value,
                                   type=self.layout.__class__.__name__)


    def _layout_axis(self, layout):
        fig = self.handles['fig']
        layout_axis = fig.add_subplot(111)
        layout_axis.patch.set_visible(False)

        # Set labels
        layout_axis.set_xlabel(str(layout.key_dimensions[0]))
        if layout.ndims == 2:
            layout_axis.set_ylabel(str(layout.key_dimensions[1]))

        # Compute and set x- and y-ticks
        keys = layout.keys()
        if layout.ndims == 1:
            dim1_keys = keys
            dim2_keys = [0]
            layout_axis.get_yaxis().set_visible(False)
        else:
            dim1_keys, dim2_keys = zip(*keys)
            layout_axis.set_ylabel(str(layout.key_dimensions[1]))
            layout_axis.set_aspect(float(self.rows)/self.cols)
        plot_width = 1.0 / self.cols
        xticks = [(plot_width/2)+(r*plot_width) for r in range(self.cols)]
        plot_height = 1.0 / self.rows
        yticks = [(plot_height/2)+(r*plot_height) for r in range(self.rows)]
        layout_axis.set_xticks(xticks)
        layout_axis.set_xticklabels(self._process_ticklabels(sorted(set(dim1_keys))))
        layout_axis.set_yticks(yticks)
        layout_axis.set_yticklabels(self._process_ticklabels(sorted(set(dim2_keys))))

        return layout_axis


    def _process_ticklabels(self, labels):
        return [k if isinstance(k, str) else np.round(float(k), 3) for k in labels]


    def _adjust_subplots(self, axis, subaxes):
        bbox = axis.get_position()
        l, b, w, h = bbox.x0, bbox.y0, bbox.width, bbox.height

        if self.cols == 1:
            b_w = 0
        else:
            b_w = (w/10.) / (self.cols - 1)

        if self.rows == 1:
            b_h = 0
        else:
            b_h = (h/10.) / (self.rows - 1)
        ax_w = (w - ((w/10.) if self.cols > 1 else 0)) / self.cols
        ax_h = (h - ((h/10.) if self.rows > 1 else 0)) / self.rows

        r, c = (0, 0)
        for ax in subaxes.values():
            xpos = l + (c*ax_w) + (c * b_w)
            ypos = b + (r*ax_h) + (r * b_h)
            if r != self.rows-1:
                r += 1
            else:
                r = 0
                c += 1
            if not ax is None:
                ax.set_position([xpos, ypos, ax_w, ax_h])


    def update_handles(self, axis, view, key, ranges=None):
        """
        Should be called by the update_frame class to update
        any handles on the plot.
        """
        axis.set_title(self._format_title(key))



class AdjointLayoutPlot(CompositePlot):
    """
    LayoutPlot allows placing up to three Views in a number of
    predefined and fixed layouts, which are defined by the layout_dict
    class attribute. This allows placing subviews next to a main plot
    in either a 'top' or 'right' position.

    Initially, a LayoutPlot computes an appropriate layout based for
    the number of Views in the AdjointLayout object it has been given, but
    when embedded in a NdLayout, it can recompute the layout to
    match the number of rows and columns as part of a larger grid.
    """

    layout_dict = {'Single':          {'width_ratios': [4],
                                       'height_ratios': [4],
                                       'positions': ['main']},
                   'Dual':            {'width_ratios': [4, 1],
                                       'height_ratios': [4],
                                       'positions': ['main', 'right']},
                   'Triple':          {'width_ratios': [4, 1],
                                       'height_ratios': [1, 4],
                                       'positions': ['top',   None,
                                                     'main', 'right']},
                   'Embedded Dual':   {'width_ratios': [4],
                                       'height_ratios': [1, 4],
                                       'positions': [None, 'main']}}

    border_size = param.Number(default=0.25, doc="""
        The size of the border expressed as a fraction of the main plot.""")

    subplot_size = param.Number(default=0.25, doc="""
        The size subplots as expressed as a fraction of the main plot.""")


    def __init__(self, layout, layout_type, subaxes, subplots, **params):
        # The AdjointLayout ViewableElement object
        self.layout = layout
        # Type may be set to 'Embedded Dual' by a call it grid_situate
        self.layout_type = layout_type
        self.view_positions = self.layout_dict[self.layout_type]['positions']

        # The supplied (axes, view) objects as indexed by position
        self.subaxes = {pos: ax for ax, pos in zip(subaxes, self.view_positions)}
        super(AdjointLayoutPlot, self).__init__(subplots=subplots, **params)


    def __call__(self, ranges=None):
        """
        Plot all the views contained in the AdjointLayout Object using axes
        appropriate to the layout configuration. All the axes are
        supplied by LayoutPlot - the purpose of the call is to
        invoke subplots with correct options and styles and hide any
        empty axes as necessary.
        """
        for pos in self.view_positions:
            # Pos will be one of 'main', 'top' or 'right' or None
            view = self.layout.get(pos, None)
            subplot = self.subplots.get(pos, None)
            ax = self.subaxes.get(pos, None)
            # If no view object or empty position, disable the axis
            if None in [view, pos, subplot]:
                ax.set_axis_off()
                continue

            vtype = view.type if isinstance(view, HoloMap) else view.__class__
            # 'Main' views that should be displayed with square aspect
            if pos == 'main' and issubclass(vtype, ViewableElement):
                subplot.aspect='square'
            subplot(ranges=ranges)
        self.drawn = True


    def adjust_positions(self):
        """
        Make adjustments to the positions of subplots (if available)
        relative to the main plot axes as required.

        This method is called by LayoutPlot after an initial pass
        used to position all the Layouts together. This method allows
        LayoutPlots to make final adjustments to the axis positions.
        """
        main_ax = self.subaxes['main']
        bbox = main_ax.get_position()
        if 'right' in self.view_positions:
            ax = self.subaxes['right']
            ax.set_position([bbox.x1 + bbox.width * self.border_size,
                             bbox.y0,
                             bbox.width * self.subplot_size, bbox.height])
        if 'top' in self.view_positions:
            ax = self.subaxes['top']
            ax.set_position([bbox.x0,
                             bbox.y1 + bbox.height * self.border_size,
                             bbox.width, bbox.height * self.subplot_size])


    def update_frame(self, key, ranges=None):
        for pos, subplot in self.subplots.items():
            if subplot is not None:
                subplot.update_frame(key, ranges)


    def __len__(self):
        return max([len(v) if isinstance(v, UniformNdMapping) else len(v.all_keys)
                    for v in self.layout if isinstance(v, (UniformNdMapping, AxisLayout))]+[1])


class LayoutPlot(CompositePlot):
    """
    A LayoutPlot accepts either a LayoutTree or a NdLayout and
    displays the elements in a cartesian grid in scanline order.
    """

    horizontal_spacing = param.Number(default=0.5, doc="""
      Specifies the space between horizontally adjacent elements in the grid.
      Default value is set conservatively to avoid overlap of subplots.""")

    vertical_spacing = param.Number(default=0.2, doc="""
      Specifies the space between vertically adjacent elements in the grid.
      Default value is set conservatively to avoid overlap of subplots.""")

    def __init__(self, layout, **params):
        if not isinstance(layout, (NdLayout, LayoutTree)):
            raise Exception("LayoutPlot only accepts LayoutTree objects.")

        self.subplots = {}
        self.rows, self.cols = layout.shape
        self.coords = list(product(range(self.rows),
                                   range(self.cols)))
        dimensions, keys = unique_dimkeys(layout)
        super(LayoutPlot, self).__init__(keys=keys, dimensions=dimensions,
                                         uniform=uniform(layout), **params)
        self.subplots, self.subaxes, self.layout = self._compute_gridspec(layout)


    def _compute_gridspec(self, layout):
        """
        Computes the tallest and widest cell for each row and column
        by examining the Layouts in the AxisLayout. The GridSpec is then
        instantiated and the LayoutPlots are configured with the
        appropriate embedded layout_types. The first element of the
        returned tuple is a dictionary of all the LayoutPlots indexed
        by row and column. The second dictionary in the tuple supplies
        the grid indicies needed to instantiate the axes for each
        LayoutPlot.
        """
        self.handles['axis'] = self._init_axis(None)
        layout_items = layout.grid_items()

        layouts, grid_indices = {}, {}
        row_heightratios, col_widthratios = {}, {}
        for (r, c) in self.coords:
            # Get view at layout position and wrap in AdjointLayout
            _, view = layout_items.get((r, c), (None, None))
            layout_view = view if isinstance(view, AdjointLayout) else AdjointLayout([view])
            layouts[(r, c)] = layout_view

            # Compute shape of AdjointLayout element
            layout_lens = {1:'Single', 2:'Dual', 3:'Triple'}
            layout_type = layout_lens[len(layout_view)]
            width_ratios = AdjointLayoutPlot.layout_dict[layout_type]['width_ratios']
            height_ratios = AdjointLayoutPlot.layout_dict[layout_type]['height_ratios']
            layout_shape = (len(width_ratios), len(height_ratios))

            # For each row and column record the width and height ratios
            # of the LayoutPlot with the most horizontal or vertical splits
            if layout_shape[0] > row_heightratios.get(r, (0, None))[0]:
                row_heightratios[r] = (layout_shape[1], height_ratios)
            if layout_shape[1] > col_widthratios.get(c, (0, None))[0]:
                col_widthratios[c] = (layout_shape[0], width_ratios)

        # In order of row/column collect the largest width and height ratios
        height_ratios = [v[1] for k, v in sorted(row_heightratios.items())]
        width_ratios = [v[1] for k, v in sorted(col_widthratios.items())]
        # Compute the number of rows and cols
        cols = np.sum([len(wr) for wr in width_ratios])
        rows = np.sum([len(hr) for hr in height_ratios])
        # Flatten the width and height ratio lists
        wr_list = [wr for wrs in width_ratios for wr in wrs]
        hr_list = [hr for hrs in height_ratios for hr in hrs]

        self.gs = gridspec.GridSpec(rows, cols,
                                    width_ratios=wr_list,
                                    height_ratios=hr_list,
                                    wspace=self.horizontal_spacing,
                                    hspace=self.vertical_spacing)

        # Situate all the Layouts in the grid and compute the gridspec
        # indices for all the axes required by each LayoutPlot.
        gidx = 0
        collapsed_layout = layout.clone(id=layout.id)
        frame_ranges = self.compute_ranges(layout, None, None)
        frame_ranges = OrderedDict([(key, self.compute_ranges(layout, key, frame_ranges))
                                    for key in self.keys])
        layout_subplots, layout_axes = {}, {}
        for (r, c) in self.coords:
            # Compute the layout type from shape
            wsplits = len(width_ratios[c])
            hsplits = len(height_ratios[r])
            if (wsplits, hsplits) == (1,1):
                layout_type = 'Single'
            elif (wsplits, hsplits) == (2,1):
                layout_type = 'Dual'
            elif (wsplits, hsplits) == (1,2):
                layout_type = 'Embedded Dual'
            elif (wsplits, hsplits) == (2,2):
                layout_type = 'Triple'

            # Get the AdjoinLayout at the specified coordinate
            view = layouts[(r, c)]
            positions = AdjointLayoutPlot.layout_dict[layout_type]['positions']

            # Create temporary subplots to get projections types
            # to create the correct subaxes for all plots in the layout
            temp_subplots, new_layout = self._create_subplots(layouts[(r, c)], positions,
                                                              frame_ranges)
            gidx, gsinds, projs = self.grid_situate(temp_subplots, gidx, layout_type, cols)

            # Generate the axes and create the subplots with the appropriate
            # axis objects
            subaxes = [plt.subplot(self.gs[ind], projection=proj)
                       for ind, proj in zip(gsinds, projs)]
            subplots, adjoint_layout = self._create_subplots(layouts[(r, c)], positions,
                                                             frame_ranges,
                                                             dict(zip(positions, subaxes)))
            layout_axes[(r, c)] = subaxes

            # Generate the AdjointLayoutsPlot which will coordinate
            # plotting of AdjointLayouts in the larger grid
            plotopts = self.lookup_options(view, 'plot').options
            layout_plot = AdjointLayoutPlot(adjoint_layout, layout_type, subaxes, subplots,
                                            figure=self.handles['fig'], **plotopts)
            layout_subplots[(r, c)] = layout_plot
            layout_key, _ = layout_items.get((r, c), (None, None))
            if layout_key:
                collapsed_layout[layout_key] = adjoint_layout

        return layout_subplots, layout_axes, collapsed_layout


    def grid_situate(self, subplots, current_idx, layout_type, subgrid_width):
        """
        Situate the current AdjointLayoutPlot in a LayoutPlot. The
        LayoutPlot specifies a layout_type into which the AdjointLayoutPlot
        must be embedded. This enclosing layout is guaranteed to have
        enough cells to display all the views.

        Based on this enforced layout format, a starting index
        supplied by LayoutPlot (indexing into a large gridspec
        arrangement) is updated to the appropriate embedded value. It
        will also return a list of gridspec indices associated with
        the all the required layout axes.
        """
        # Set the layout configuration as situated in a NdLayout

        if layout_type == 'Single':
            positions = ['main']
            start, inds = current_idx+1, [current_idx]
        elif layout_type == 'Dual':
            positions = ['main', 'right']
            start, inds = current_idx+2, [current_idx, current_idx+1]

        bottom_idx = current_idx + subgrid_width
        if layout_type == 'Embedded Dual':
            positions = [None, None, 'main', 'right']
            bottom = ((current_idx+1) % subgrid_width) == 0
            grid_idx = (bottom_idx if bottom else current_idx)+1
            start, inds = grid_idx, [current_idx, bottom_idx]
        elif layout_type == 'Triple':
            positions = ['top', None, 'main', 'right']
            bottom = ((current_idx+2) % subgrid_width) == 0
            grid_idx = (bottom_idx if bottom else current_idx) + 2
            start, inds = grid_idx, [current_idx, current_idx+1,
                              bottom_idx, bottom_idx+1]
        projs = [subplots.get(pos, Plot).projection for pos in positions]

        return start, inds, projs


    def _create_subplots(self, layout, positions, ranges, axes={}):
        """
        Plot all the views contained in the AdjointLayout Object using axes
        appropriate to the layout configuration. All the axes are
        supplied by LayoutPlot - the purpose of the call is to
        invoke subplots with correct options and styles and hide any
        empty axes as necessary.
        """
        subplots = {}
        adjoint_clone = layout.clone(id=layout.id)
        subplot_opts = dict(show_title=False, layout=layout)
        for pos in positions:
            # Pos will be one of 'main', 'top' or 'right' or None
            view = layout.get(pos, None)
            ax = axes.get(pos, None)
            if view is None:
                continue
            # Customize plotopts depending on position.
            plotopts = self.lookup_options(view, 'plot').options
            # Options common for any subplot

            override_opts = {}
            if pos == 'right':
                right_opts = dict(orientation='vertical', show_xaxis=None, show_yaxis='left')
                override_opts = dict(subplot_opts, **right_opts)
            elif pos == 'top':
                top_opts = dict(show_xaxis='bottom', show_yaxis=None)
                override_opts = dict(subplot_opts, **top_opts)

            # Override the plotopts as required
            plotopts.update(override_opts, figure=self.handles['fig'])
            vtype = view.type if isinstance(view, HoloMap) else view.__class__
            layer_types = (vtype,) if isinstance(view, ViewableElement) else view.layer_types
            if isinstance(view, AxisLayout):
                if len(layer_types) == 1 and issubclass(layer_types[0], Raster):
                    from .raster import MatrixGridPlot
                    plot_type = MatrixGridPlot
                else:
                    plot_type = GridPlot
            else:
                if pos == 'main':
                    plot_type = Plot.defaults[vtype]
                else:
                    plot_type = Plot.sideplots[vtype]

            subplots[pos] = plot_type(view, axis=ax, ranges=ranges,
                                      dimensions=self.dimensions,
                                      uniform=self.uniform,
                                      keys=self.keys, **plotopts)
            adjoint_clone[pos] = subplots[pos].map
        return subplots, adjoint_clone


    def __call__(self):
        self.handles['axis'].get_xaxis().set_visible(False)
        self.handles['axis'].get_yaxis().set_visible(False)

        ranges = self.compute_ranges(self.layout, self.keys[-1], None)
        rcopts = self.lookup_options(self.layout, 'style').options
        for subplot in self.subplots.values():
            with matplotlib.rc_context(rcopts):
                subplot(ranges=ranges)
        plt.draw()

        # Adjusts the AdjointLayout subplot positions
        for (r, c) in self.coords:
            self.subplots.get((r, c), None).adjust_positions()

        return self._finalize_axis(None)


Plot.defaults.update({AxisLayout: GridPlot,
                      NdLayout: LayoutPlot,
                      LayoutTree: LayoutPlot,
                      AdjointLayout: AdjointLayoutPlot})
