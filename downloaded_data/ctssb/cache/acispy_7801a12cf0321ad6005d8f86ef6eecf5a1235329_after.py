from Ska.Matplotlib import plot_cxctime, pointpair, \
    cxctime2plotdate
from matplotlib import font_manager
import matplotlib.pyplot as plt
from matplotlib.dates import num2date
from acispy.utils import unit_labels, ensure_list
from Chandra.Time import DateTime
from datetime import datetime
from collections import OrderedDict
from matplotlib.backends.backend_agg import \
    FigureCanvasAgg
from io import BytesIO
from mpl_toolkits.axes_grid1 import make_axes_locatable
from acispy.utils import convert_state_code
import numpy as np

drawstyles = {"simpos": "steps",
              "pitch": "steps",
              "ccd_count": "steps",
              "fmt": "steps"}

units_map = {"deg_C": "Temperature",
             "V": "Voltage",
             "A": "Current",
             "W": "Power",
             "deg": 'Angle',
             "deg**2": "Solid Angle"}

default_colors = ["b","r","g","k"]

class ACISPlot(object):
    def __init__(self, fig, ax):
        self.fig = fig
        self.ax = ax

    def _repr_png_(self):
        canvas = FigureCanvasAgg(self.fig)
        f = BytesIO()
        canvas.print_figure(f)
        f.seek(0)
        return f.read()

    def savefig(self, filename, **kwargs):
        """
        Save the figure to the file specified by *filename*.
        """
        self.fig.savefig(filename, **kwargs)

    def set_title(self, label, fontsize=18, loc='center', **kwargs):
        """
        Add a title to the top of the plot.

        Parameters
        ----------
        label : string
            The title itself.
        fontsize : integer, optional
            The size of the font. Default: 18 pt
        loc : string, optional
            The horizontal location of the title. Options are: 'left',
            'right', 'center'. Default: 'center'

        Examples
        --------
        >>> p.set_title("my awesome plot", fontsize=15, loc='left')
        """
        fontdict = {"family": "serif", "size": fontsize}
        self.ax.set_title(label, fontdict=fontdict, loc=loc, **kwargs)

    def set_grid(self, on):
        """
        Turn grid lines on or off on the plot. 

        Parameters
        ----------
        on : boolean
            Set to True to put the lines on, set to False to remove them.
        """
        self.ax.grid(on)

    def add_hline(self, y, lw=2, ls='-', color='green', **kwargs):
        """
        Add a horizontal line on the y-axis of the plot.

        Parameters
        ----------
        y : float
            The value to place the vertical line at.
        lw : integer, optional
            The width of the line. Default: 2
        ls : string, optional
            The style of the line. Can be one of:
            'solid', 'dashed', 'dashdot', 'dotted'.
            Default: 'solid'
        color : string, optional
            The color of the line. Default: 'green'

        Examples
        --------
        >>> p.add_hline(36., lw=3, ls='dashed', color='red')
        """
        self.ax.axhline(y=y, lw=lw, ls=ls, color=color, **kwargs)

    def set_ylim(self, ymin, ymax):
        """
        Set the limits on the left y-axis of the plot to *ymin* and *ymax*.
        """
        self.ax.set_ylim(ymin, ymax)

    def set_ylabel(self, ylabel, fontsize=18, **kwargs):
        """
        Set the label of the left y-axis of the plot.

        Parameters
        ----------
        ylabel : string
            The new label.
        fontsize : integer, optional
            The size of the font. Default: 18 pt

        Examples
        --------
        >>> pp.set_ylabel("DPA Temperature", fontsize=15)
        """
        fontdict = {"size": fontsize, "family": "serif"}
        self.ax.set_ylabel(ylabel, fontdict=fontdict, **kwargs)

    def redraw(self):
        """
        Re-draw the plot.
        """
        self.fig.canvas.draw()

    def tight_layout(self, *args, **kwargs):
        self.fig.tight_layout(*args, **kwargs)

class CustomDatePlot(ACISPlot):
    r"""
    Make a custom date vs. value plot.

    Parameters
    ----------
    dates : array of strings
        The dates to be plotted.
    values : array
        The values to be plotted.
    lw : float, optional
        The width of the lines in the plots. Default: 1.5 px.
    fontsize : integer, optional
        The font size for the labels in the plot. Default: 18 pt.
    fig : :class:`~matplotlib.figure.Figure`, optional
        A Figure instance to plot in. Default: None, one will be
        created if not provided.
    ax : :class:`~matplotlib.axes.Axes`, optional
        An Axes instance to plot in. Default: None, one will be
        created if not provided.

    """
    def __init__(self, dates, values, lw=1.5, fontsize=18, fig=None, ax=None, **kwargs):
        if fig is None:
            fig = plt.figure(figsize=(10, 8))
        dates = DateTime(dates).secs
        ticklocs, fig, ax = plot_cxctime(dates, np.array(values), fig=fig, ax=ax, lw=lw, **kwargs)
        super(CustomDatePlot, self).__init__(fig, ax)
        self.ax.set_xlabel("Date", fontdict={"size": fontsize, "family": "serif"})
        fontProperties = font_manager.FontProperties(family="serif",
                                                     size=fontsize)
        for label in self.ax.get_xticklabels():
            label.set_fontproperties(fontProperties)
        for label in self.ax.get_yticklabels():
            label.set_fontproperties(fontProperties)

    def set_xlim(self, xmin, xmax):
        """
        Set the limits on the x-axis of the plot to *xmin* and *xmax*,
        which must be in YYYY:DOY:HH:MM:SS format.

        Examples
        --------
        >>> p.set_xlim("2016:050:12:45:47.324", "2016:056:22:32:01.123")
        """
        if not isinstance(xmin, datetime):
            xmin = datetime.strptime(DateTime(xmin).iso, "%Y-%m-%d %H:%M:%S.%f")
        if not isinstance(xmax, datetime):
            xmax = datetime.strptime(DateTime(xmax).iso, "%Y-%m-%d %H:%M:%S.%f")
        self.ax.set_xlim(xmin, xmax)

    def add_vline(self, time, lw=2, ls='solid', color='green', **kwargs):
        """
        Add a vertical line on the time axis of the plot.

        Parameters
        ----------
        time : string
            The time to place the vertical line at.
            Must be in YYYY:DOY:HH:MM:SS format.
        lw : integer, optional
            The width of the line. Default: 2
        ls : string, optional
            The style of the line. Can be one of:
            'solid', 'dashed', 'dashdot', 'dotted'.
            Default: 'solid'
        color : string, optional
            The color of the line. Default: 'green'

        Examples
        --------
        >>> p.add_vline("2016:101:12:36:10.102", lw=3, ls='dashed', color='red')
        """
        time = datetime.strptime(DateTime(time).iso, "%Y-%m-%d %H:%M:%S.%f")
        self.ax.axvline(x=time, lw=lw, ls=ls, color=color, **kwargs)

    def add_text(self, time, y, text, fontsize=18, color='black',
                 rotation='horizontal', **kwargs):
        """
        Add text to a DatePlot.

        Parameters
        ----------
        time : string
            The time to place the text at.
            Must be in YYYY:DOY:HH:MM:SS format.
        y : float
            The y-value to place the text at.
        text : string
            The text itself.
        fontsize : integer, optional
            The size of the font. Default: 18 pt.
        color : string, optional
            The color of the font. Default: black.
        rotation : string or float, optional
            The rotation of the text. Default: Horizontal

        Examples
        --------
        >>> dp.add_text("2016:101:12:36:10.102", 35., "Something happened here!",
        ...             fontsize=15, color='magenta')
        """
        time = datetime.strptime(DateTime(time).iso, "%Y-%m-%d %H:%M:%S.%f")
        self.ax.text(time, y, text, fontsize=fontsize, color=color,
                     family='serif', rotation=rotation, **kwargs)

    def set_line_label(self, line, label):
        """
        Change the field label in the legend.

        Parameters
        ----------
        line : integer
            The line whose label to change given by its number, assuming
            a starting index of 0.
        label :
            The label to set it to.

        Examples
        --------
        >>> dp.set_line_label(1, "DEA Temperature")
        """
        self.ax.lines[line].set_label(label)
        self.set_legend()

    def set_legend(self, loc='best', fontsize=16, **kwargs):
        """
        Adjust a legend on the plot.

        Parameters
        ----------
        loc : string, optional
            The location of the legend on the plot. Options are:
            'best'
            'upper right'
            'upper left'
            'lower left'
            'lower right'
            'right'
            'center left'
            'center right'
            'lower center'
            'upper center'
            'center'
            Default: 'best', which will try to find the best location for
            the legend, e.g. away from plotted data.
        fontsize : integer, optional
            The size of the legend text. Default: 16 pt.

        Examples
        --------
        >>> p.set_legend(loc='right', fontsize=18)
        """
        prop = {"family": "serif", "size": fontsize}
        self.ax.legend(loc=loc, prop=prop, **kwargs)

class DatePlot(CustomDatePlot):
    r""" Make a single-panel plot of a quantity (or multiple quantities) 
    vs. date and time. 

    Multiple quantities can be plotted on the left
    y-axis together if they have the same units, otherwise a quantity
    with different units can be plotted on the right y-axis. 

    Parameters
    ----------
    dc : :class:`~acispy.data_container.DataContainer`
        The DataContainer instance to get the data to plot from.
    fields : tuple of strings or list of tuples of strings
        A single field or list of fields to plot on the left y-axis.
    field2 : tuple of strings, optional
        A single field to plot on the right y-axis. Default: None
    lw : float, optional
        The width of the lines in the plots. Default: 1.5 px.
    fontsize : integer, optional
        The font size for the labels in the plot. Default: 18 pt.
    colors : list of strings, optional
        The colors for the lines plotted on the left y-axis.
        Default: ["blue", "red", "green", "black"]
    color2 : string, optional
        The color for the line plotted on the right y-axis.
        Default: "magenta"
    fig : :class:`~matplotlib.figure.Figure`, optional
        A Figure instance to plot in. Default: None, one will be
        created if not provided.
    ax : :class:`~matplotlib.axes.Axes`, optional
        An Axes instance to plot in. Default: None, one will be
        created if not provided.

    Examples
    --------
    >>> from acispy import DatePlot
    >>> p1 = DatePlot(dc, ("msids", "1dpamzt"), field2=("states", "pitch"),
    ...               lw=2, colors="brown")

    >>> from acispy import DatePlot
    >>> fields = [("msids", "1dpamzt"), ("msids", "1deamzt"), ("msids", "1pdeaat")]
    >>> p2 = DatePlot(dc, fields, fontsize=12, colors=["brown","black","orange"])
    """
    def __init__(self, dc, fields, field2=None, lw=1.5, fontsize=18,
                 colors=None, color2='magenta', fig=None, ax=None):
        if fig is None:
            fig = plt.figure(figsize=(10, 8))
        if colors is None:
            colors = default_colors
        fields = ensure_list(fields)
        self.fields = fields
        self.num_fields = len(fields)
        colors = ensure_list(colors)
        self.times = {}
        self.y = {}
        for i, field in enumerate(fields):
            src_name, fd = field
            drawstyle = drawstyles.get(fd, None)
            state_codes = dc.state_codes.get(field, None)
            if state_codes is None:
                y = dc[field].value
            else:
                state_codes = [(v, k) for k, v in state_codes.items()]
                y = convert_state_code(dc, field)
            if src_name == "states":
                tstart, tstop = dc[field].times
                x = pointpair(tstart.value, tstop.value)
                y = pointpair(y)
            else:
                x = dc[field].times.value
            label = dc.fields[field].display_name
            ticklocs, fig, ax = plot_cxctime(x, y, fig=fig, lw=lw, ax=ax,
                                             color=colors[i],
                                             state_codes=state_codes,
                                             drawstyle=drawstyle, 
                                             label=label)
            self.y[field] = dc[field]
            self.times[field] = dc[field].times

        self.fig = fig
        self.ax = ax
        self.dc = dc
        self.ax.set_xlabel("Date", fontdict={"size": fontsize,
                                             "family": "serif"})
        if self.num_fields > 1:
            self.ax.legend(loc=0, prop={"family": "serif"})
        fontProperties = font_manager.FontProperties(family="serif",
                                                     size=fontsize)
        for label in self.ax.get_xticklabels():
            label.set_fontproperties(fontProperties)
        for label in self.ax.get_yticklabels():
            label.set_fontproperties(fontProperties)
        ymin, ymax = self.ax.get_ylim()
        self.ax.set_ylim(0.9 * ymin, 1.1 * ymax)
        units = dc.fields[fields[0]].units
        if self.num_fields > 1:
            if units == '':
                ylabel = ''
            else:
                ylabel = '%s (%s)' % (units_map[units], unit_labels.get(units, units))
            self.set_ylabel(ylabel)
        else:
            ylabel = dc.fields[fields[0]].display_name
            if units != '':
                ylabel += ' (%s)' % unit_labels.get(units, units)
            self.set_ylabel(ylabel)
        self.field2 = field2
        if field2 is not None:
            src_name2, fd2 = field2
            self.ax2 = self.ax.twinx()
            drawstyle = drawstyles.get(fd2, None)
            state_codes = dc.state_codes.get(field2, None)
            if state_codes is None:
                y2 = dc[field2].value
            else:
                state_codes = [(v, k) for k, v in state_codes.items()]
                y2 = convert_state_code(dc, field2)
            if src_name2 == "states":
                tstart, tstop = dc[field2].times
                x = pointpair(tstart.value, tstop.value)
                y2 = pointpair(y2)
            else:
                x = dc[field2].times.value
            plot_cxctime(x, y2, fig=fig, ax=self.ax2, lw=lw,
                         drawstyle=drawstyle, color=color2,
                         state_codes=state_codes)
            self.times[field2] = dc[field2].times
            self.y[field2] = dc[field2]
            for label in self.ax2.get_xticklabels():
                label.set_fontproperties(fontProperties)
            for label in self.ax2.get_yticklabels():
                label.set_fontproperties(fontProperties)
            ymin2, ymax2 = self.ax2.get_ylim()
            self.ax2.set_ylim(0.9*ymin2, 1.1*ymax2)
            units2 = dc.fields[field2].units
            ylabel2 = dc.fields[field2].display_name
            if units2 != '':
                ylabel2 += ' (%s)' % unit_labels.get(units2, units2)
            self.set_ylabel2(ylabel2)
        self._fill_bad_times()

    def _fill_bad_times(self):
        masks = []
        times = []
        for field in self.fields:
            if field[0] != "states":
                times.append(self.times[field])
                masks.append(self.y[field].mask)
        axes = [self.ax]*len(times)
        if self.field2 and self.field2[0] != "states":
            axes.append(self.ax2)
            times.append(self.times[self.field2])
            masks.append(self.y[self.field2].mask)
        for mask, ax, x in zip(masks, axes, times):
            if np.any(~mask):
                ybot, ytop = ax.get_ylim()
                all_time = cxctime2plotdate(x.value)
                bad = np.concatenate([[False], ~mask, [False]])
                bad_int = np.flatnonzero(bad[1:] != bad[:-1]).reshape(-1, 2)
                for ii, jj in bad_int:
                    ax.fill_between(all_time[ii:jj], ybot, ytop, 
                                    where=~mask[ii:jj], color='cyan', alpha=0.5)

    def set_ylim(self, ymin, ymax):
        """
        Set the limits on the left y-axis of the plot to *ymin* and *ymax*.
        """
        self.ax.set_ylim(ymin, ymax)
        self._fill_bad_times()

    def set_ylim2(self, ymin, ymax):
        """
        Set the limits on the right y-axis of the plot to *ymin* and *ymax*.
        """
        self.ax2.set_ylim(ymin, ymax)
        self._fill_bad_times()

    def set_ylabel2(self, ylabel, fontsize=18, **kwargs):
        """
        Set the label of the right y-axis of the plot.

        Parameters
        ----------
        ylabel : string
            The new label.
        fontsize : integer, optional
            The size of the font. Default: 18 pt

        Examples
        --------
        >>> p1.set_ylabel2("Pitch Angle in Degrees", fontsize=14)
        """
        fontdict = {"size": fontsize, "family": "serif"}
        self.ax2.set_ylabel(ylabel, fontdict=fontdict, **kwargs)

    def add_hline2(self, y2, lw=2, ls='solid', color='green', **kwargs):
        """
        Add a horizontal line on the right y-axis of the plot.

        Parameters
        ----------
        y2 : float
            The value to place the vertical line at.
        lw : integer, optional
            The width of the line. Default: 2
        ls : string, optional
            The style of the line. Can be one of:
            'solid', 'dashed', 'dashdot', 'dotted'.
            Default: 'solid'
        color : string, optional
            The color of the line. Default: 'green'

        Examples
        --------
        >>> p.add_hline2(105., lw=3, ls='dashed', color='red')
        """
        self.ax2.axhline(y=y2, lw=lw, ls=ls, color=color, **kwargs)

    def set_field_label(self, field, label):
        """
        Change the field label in the legend.

        Parameters
        ----------
        field : (type, name) tuple
            The field whose label to change.
        label :
            The label to set it to.

        Examples
        --------
        >>> dp.set_field_label(("msids","1deamzt"), "DEA Temperature")
        """
        idx = self.fields.index(field)
        self.set_line_label(idx, label)

class MultiDatePlot(object):
    r""" Make a multi-panel plot of multiple quantities vs. date and time.

    Parameters
    ----------
    dc : :class:`~acispy.data_container.DataContainer`
        The DataContainer instance to get the data to plot from.
    fields : list of tuples of strings
        A list of fields to plot.
    subplots : tuple of integers, optional
        The gridded layout of the plots, i.e. (num_x_plots, num_y_plots)
        The default is to have all plots stacked vertically.
    fontsize : integer, optional
        The font size for the labels in the plot. Default: 15 pt.
    lw : float, optional
        The width of the lines in the plots. Default: 1.5 px.
    fig : :class:`~matplotlib.figure.Figure`, optional
        A Figure instance to plot in. Default: None, one will be
        created if not provided.

    Examples
    --------
    >>> from acispy import MultiDatePlot
    >>> fields = [("msids", "1deamzt"), ("model", "1deamzt"), ("states", "ccd_count")]
    >>> mp = MultiDatePlot(dc, fields, lw=2, subplots=(2, 2))

    >>> from acispy import MultiDatePlot
    >>> fields = [[("msids", "1deamzt"), ("model", "1deamzt")], ("states", "ccd_count")]
    >>> mp = MultiDatePlot(dc, fields, lw=2)
    """
    def __init__(self, dc, fields, subplots=None,
                 fontsize=15, lw=1.5, fig=None):
        if fig is None:
            fig = plt.figure(figsize=(12, 12))
        if subplots is None:
            subplots = len(fields), 1
        self.plots = OrderedDict()
        for i, field in enumerate(fields):
            ax = fig.add_subplot(subplots[0], subplots[1], i+1)
            if isinstance(field, list):
                fd = field[0]
            else:
                fd = field
            self.plots[fd] = DatePlot(dc, field, fig=fig, ax=ax, lw=lw)
            ax.xaxis.label.set_size(fontsize)
            ax.yaxis.label.set_size(fontsize)
            ax.xaxis.set_tick_params(labelsize=fontsize)
            ax.yaxis.set_tick_params(labelsize=fontsize)
        self.fig = fig
        xmin, xmax = self.plots[self.plots.keys()[0]].ax.get_xlim()
        self.set_xlim(num2date(xmin), num2date(xmax))

    def __getitem__(self, item):
        return self.plots[item]

    def set_xlim(self, xmin, xmax):
        """
        Set the limits on the x-axis of the plot to *xmin* and *xmax*,
        which must be in YYYY:DOY:HH:MM:SS format.
        """
        for plot in self.plots.values():
            plot.set_xlim(xmin, xmax)

    def add_vline(self, x, lw=2, ls='-', color='green', **kwargs):
        """
        Add a vertical line on the time axis of the plot.

        Parameters
        ----------
        time : string
            The time to place the vertical line at.
            Must be in YYYY:DOY:HH:MM:SS format.
        lw : integer, optional
            The width of the line. Default: 2
        ls : string, optional
            The style of the line. Can be one of:
            'solid', 'dashed', 'dashdot', 'dotted'.
            Default: 'solid'
        color : string, optional
            The color of the line. Default: 'green'

        Examples
        --------
        >>> p.add_vline("2016:101:12:36:10.102", lw=3, ls='dashed', color='red')
        """
        for plot in self.plots.values():
            plot.add_vline(x, lw=lw, ls=ls, color=color, **kwargs)

    def set_title(self, label, fontsize=18, loc='center', **kwargs):
        """
        Add a title to the top of the plot.

        Parameters
        ----------
        label : string
            The title itself.
        fontsize : integer, optional
            The size of the font. Default: 18 pt
        loc : string, optional
            The horizontal location of the title. Options are: 'left',
            'right', 'center'. Default: 'center'

        Examples
        --------
        >>> p.set_title("my awesome plot", fontsize=15, loc='left')
        """
        self.plots.values()[0].set_title(label, fontsize=fontsize, loc=loc, **kwargs)

    def set_grid(self, on):
        """
        Turn grid lines on or off on the plot. 

        Parameters
        ----------
        on : boolean
            Set to True to put the lines on, set to False to remove them.
        """
        for plot in self.plots.values():
            plot.set_grid(on)

    def savefig(self, filename, **kwargs):
        """
        Save the figure to the file specified by *filename*.
        """
        self.fig.savefig(filename, **kwargs)

    def _repr_png_(self):
        canvas = FigureCanvasAgg(self.fig)
        f = BytesIO()
        canvas.print_figure(f)
        f.seek(0)
        return f.read()

    def redraw(self):
        """
        Re-draw the plot.
        """
        self.fig.canvas.draw()

class PhasePlot(ACISPlot):
    r""" Make a single-panel plot of one quantity vs. another.

    The one restriction is that you cannot plot a state on the y-axis
    if the quantity on the x-axis is not a state. 

    Parameters
    ----------
    dc : :class:`~acispy.data_container.DataContainer`
        The DataContainer instance to get the data to plot from.
    x_field : tuple of strings
        The field to plot on the x-axis.
    y_field : tuple of strings
        The field to plot on the y-axis.
    c_field : tuple of strings, optional
        The field to use to color the dots on the plot. Default: None
    fontsize : integer, optional
        The font size for the labels in the plot. Default: 18 pt.
    color : string, optional
        The color of the dots on the phase plot. Only used if a
        color field is not provided. Default: 'blue'
    cmap : string, optional
        The colormap for the dots if a color field has been provided.
        Default: 'heat'
    fig : :class:`~matplotlib.figure.Figure`, optional
        A Figure instance to plot in. Default: None, one will be
        created if not provided.
    ax : :class:`~matplotlib.axes.Axes`, optional
        An Axes instance to plot in. Default: None, one will be
        created if not provided.

    Examples
    --------
    >>> from acispy import PhasePlot
    >>> pp = PhasePlot(dc, ("msids", "1deamzt"), ("msids", "1dpamzt"))
    """
    def __init__(self, dc, x_field, y_field, c_field=None,
                 fontsize=18, color='blue', cmap='hot',
                 fig=None, ax=None, **kwargs):
        if fig is None:
            fig = plt.figure(figsize=(12, 12))
        if ax is None:
            ax = fig.add_subplot(111)

        xlabel = dc.fields[x_field].display_name
        ylabel = dc.fields[y_field].display_name
        xunit = dc.fields[x_field].units
        yunit = dc.fields[y_field].units

        self.xx = dc[x_field]
        self.yy = dc[y_field]

        if c_field is None:
            self.cc = color
        else:
            self.cc = dc[c_field]

        cm = plt.cm.get_cmap(cmap)
        scp = ax.scatter(np.array(self.xx), np.array(self.yy),
                         c=self.cc, cmap=cm, **kwargs)

        super(PhasePlot, self).__init__(fig, ax)
        self.scp = scp

        fontProperties = font_manager.FontProperties(family="serif",
                                                     size=fontsize)
        for label in self.ax.get_xticklabels():
            label.set_fontproperties(fontProperties)
        for label in self.ax.get_yticklabels():
            label.set_fontproperties(fontProperties)
        if xunit != '':
            xlabel += ' (%s)' % unit_labels.get(xunit, xunit)
        if yunit != '':
            ylabel += ' (%s)' % unit_labels.get(yunit, yunit)
        self.set_xlabel(xlabel)
        self.set_ylabel(ylabel)
        if c_field is not None:
            clabel = dc.fields[c_field].display_name
            cunit = dc.fields[c_field].units
            if cunit != '':
                clabel += ' (%s)' % unit_labels.get(cunit, cunit)
            divider = make_axes_locatable(ax)
            cax = divider.append_axes("right", size="5%", pad=0.05)
            cb = plt.colorbar(scp, cax=cax)
            fontdict = {"family": "serif", "size": fontsize}
            cb.set_label(clabel, fontdict=fontdict)
            for label in cb.ax.get_yticklabels():
                label.set_fontproperties(fontProperties)
            self.cb = cb

    def set_xlim(self, xmin, xmax):
        """
        Set the limits on the x-axis of the plot to *xmin* and *xmax*.
        """
        self.ax.set_xlim(xmin, xmax)

    def set_xlabel(self, xlabel, fontsize=18, **kwargs):
        """
        Set the label of the x-axis of the plot.

        Parameters
        ----------
        xlabel : string
            The new label.
        fontsize : integer, optional
            The size of the font. Default: 18 pt

        Examples
        --------
        >>> pp.set_xlabel("DEA Temperature", fontsize=15)
        """
        fontdict = {"size": fontsize, "family": "serif"}
        self.ax.set_xlabel(xlabel, fontdict=fontdict, **kwargs)

    def add_vline(self, x, lw=2, ls='-', color='green', **kwargs):
        """
        Add a vertical line on the x-axis of the plot.

        Parameters
        ----------
        x : float
            The value to place the vertical line at.
        lw : integer, optional
            The width of the line. Default: 2
        ls : string, optional
            The style of the line. Can be one of:
            'solid', 'dashed', 'dashdot', 'dotted'.
            Default: 'solid'
        color : string, optional
            The color of the line. Default: 'green'

        Examples
        --------
        >>> p.add_vline(25., lw=3, ls='dashed', color='red')
        """
        self.ax.axvline(x=x, lw=lw, ls=ls, color=color, **kwargs)

    def add_text(self, x, y, text, fontsize=18, color='black', 
                 rotation='horizontal', **kwargs):
        """
        Add text to a PhasePlot.

        Parameters
        ----------
        x : string
            The x-value to place the text at.
        y : float
            The y-value to place the text at.
        text : string
            The text itself.
        fontsize : integer, optional
            The size of the font. Default: 18 pt.
        color : string, optional
            The color of the font. Default: black.
        rotation : string or float, optional
            The rotation of the text. Default: Horizontal

        Examples
        --------
        >>> dp.add_text(32.7, 35., "This spot is interesting",
        ...             fontsize=15, color='magenta')
        """
        self.ax.text(x, y, text, fontsize=fontsize, color=color,
                     family='serif', rotation=rotation, **kwargs)
