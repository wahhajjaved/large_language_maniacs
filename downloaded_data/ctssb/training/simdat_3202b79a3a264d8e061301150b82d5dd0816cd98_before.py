import numpy as np
import matplotlib.pyplot as plt
import matplotlib.mlab as mlab
from simdat.core import tools
from sklearn.metrics import confusion_matrix


class COLORS:
    red = ['#7E3517', '#954535', '#8C001A', '#C11B17',
           '#C04000', '#F62217', '#E55B3C',
           '#E78A61', '#FAAFBE', '#FFDFDD']

    grey = ['#0C090A', '#2C3539', '#413839', '#504A4B',
            '#666362', '#646D7E', '#6D7B8D',
            '#837E7C', '#D1D0CE', '#E5E4E2']

    brown = ['#493D26', '#7F462C', '#7F5217', '#B87333',
             '#C58917', '#C7A317', '#FFDB58',
             '#FFE87C', '#FFFFC2', '#F5F5DC']

    green = ['#254117', '#306754', '#437C17', '#728C00',
             '#4E9258', '#41A317', '#4CC417',
             '#99C68E', '#B2C248', '#C3FDB8']

    pink = ['#7F525D', '#C12267', '#E45E9D', '#FC6C85',
            '#F778A1', '#E38AAE', '#E799A3',
            '#FBBBB9', '#FFDFDD', '#FCDFFF']

    blue = ['#4863A0', '#737CA1', '#488AC7', '#98AFC7',
            '#38ACE7', '#659EC7', '#79BAE7',
            '#A0CFEC', '#C6DEFF', '#BDEDFF']


class PLOT(tools.DATA, COLORS):
    def tools_init(self):
        self.ax = plt.axes()

    def check_array_length(self, arrays):
        """Check if lengths of all arrays are equal

        @param arrays: input list of arrays

        @return length: the length of all arrays

        """
        length = len(arrays[0])
        for a in arrays[1:]:
            if len(a) != length:
                print('ERROR: array lengths are not equal')
                sys.exti()
        return length

    def find_axis_max_min(self, values, s_up=0.1, s_down=0.1):
        """Find max and min values used for setting axis"""

        import math
        values = self.conv_to_np(values)

        axis_max = np.amax(values)
        axis_max = axis_max + s_up
        axis_min = np.amin(values)
        axis_min = axis_min - s_down

        return axis_max, axis_min

    def scale(self, a):
        """Use no.linalg.norm to normalize the numpy array"""

        a = self.conv_to_np(a)
        return a / np.linalg.norm(a)

    def open_img(self, imgpath, clear=False):
        """Open an image on panel

        @param imgpath: path of the image

        Keyword arguments:
        clear     -- true to clear panel after output (default: False)

        @return image object and (xmax, ymax)

        """
        import matplotlib.image as mpimg
        img = mpimg.imread(imgpath)
        xmax = len(img[0])
        ymax = len(img)
        print('x max = %i, y max = %i' % (xmax, ymax))
        plt.imshow(img)
        if clear:
            plt.cla()
        return img, (xmax, ymax)

    def patch_line(self, x, y, color='#7D0552', clear=True,
                   linewidth=None, linestype='solid',
                   fname='./patch_line.png'):
        """Patch a line to the existing panel

        @param x: x data, should be a list with two elements
        @param y: y data, should be a list with two elements

        Keyword arguments:
        color     -- line color (default: #7D0552)
        clear     -- true to clear panel after output (default: True)
        linewidth -- width of the edge line
        linestype -- style of the edge, solid (default), dashed,
                     dashdot, dotted
        fname     -- output filename (default: './patch_line.png')

        """

        args = {'color': color,
                'linestyle': linestype}
        if linewidth is not None:
            args['linewidth'] = linewidth
        currentAxis = plt.gca()
        currentAxis.add_line(plt.Line2D(x, y, **args))
        if fname is not None:
            plt.savefig(fname)
        if clear:
            plt.cla()

    def patch_arrow(self, x, y, dx=20, dy=100, width=10,
                    color='#566D7E', fill=False, clear=True,
                    linewidth=None, linestype='dashed',
                    fname='./patch_arrow.png'):
        """Patch a arrow to the existing panel

        @param x: the starting point of x axis
        @param y: the starting point of y axis

        Keyword arguments:
        dx        -- delta x of the arrow
        dy        -- delta y of the arrow
        width     -- width of the arrow
        color     -- arrow color (default: #566D7E)
        fill      -- true to fill the arrow (defaule: False)
        clear     -- true to clear panel after output (default: True)
        linewidth -- width of the edge line
        linestype -- style of the edge, solid, dashed (default),
                     dashdot, dotted
        fname     -- output filename (default: './patch_arrow.png')

        """
        from matplotlib.patches import Arrow
        args = {'edgecolor': color,
                'width': width,
                'linestyle': linestype}
        if fill:
            args['facecolor'] = color
            args['linestyle'] = 'solid'
        else:
            args['facecolor'] = 'none'
        if linewidth is not None:
            args['linewidth'] = linewidth
        currentAxis = plt.gca()
        currentAxis.add_patch(Arrow(x, y, dx, dy, **args))
        if fname is not None:
            plt.savefig(fname)
        if clear:
            plt.cla()

    def patch_textbox(self, x, y, text, style='round',
                      textcolor='#565051', edgecolor='#565051',
                      clear=True, fname='./patch_textbox.png'):
        """Patch a textbox to the existing panel

        @param x: the starting point of x axis
        @param y: the starting point of y axis
        @param text: text to show

        Keyword arguments:
        style     -- style of the bbox (default: round)
        textcolor -- color of the text (default: #565051)
        edgecolor -- color of the edge (default: #565051)
        clear     -- true to clear panel after output (default: True)
        fname     -- output filename (default: './patch_textbox.png')

        """
        args = {'edgecolor': edgecolor,
                'boxstyle': style,
                'facecolor': 'none'}
        self.ax.text(x, y, text, color=textcolor, bbox=args)
        if fname is not None:
            plt.savefig(fname)
        if clear:
            plt.cla()

    def patch_circle(self, x, y, radius=3,
                     color='#E77471', fill=False, clear=True,
                     linewidth=None, linestype='dashed',
                     fname='./patch_circle.png'):
        """Patch a circle to the existing panel"""

        self.patch_ellipse(x, y, w=radius, h=radius,
                           color=color, fill=fill, clear=clear,
                           linewidth=linewidth, linestype=linestype,
                           fname=fname)

    def patch_ellipse(self, x, y, w=5, h=3, angle=0,
                      color='#E77471', fill=False, clear=True,
                      linewidth=None, linestype='dashed',
                      fname='./patch_ellipse.png'):
        """Patch a ellipse to the existing panel

        @param x: the starting point of x axis
        @param y: the starting point of y axis

        Keyword arguments:
        w         -- width of the ellipse
        h         -- height of the ellipse
        angle     -- rotation angle of the ellipse (default: 0)
        color     -- ellipse color (default: #E77471)
        fill      -- true to fill the ellipse (defaule: False)
        clear     -- true to clear panel after output (default: True)
        linewidth -- width of the edge line
        linestype -- style of the edge, solid, dashed (default),
                     dashdot, dotted
        fname     -- output filename (default: './patch_ellipse.png')

        """
        from matplotlib.patches import Ellipse
        args = {'edgecolor': color,
                'angle': angle,
                'linestyle': linestype}
        if fill:
            args['facecolor'] = color
            args['linestyle'] = 'solid'
        else:
            args['facecolor'] = 'none'
        if linewidth is not None:
            args['linewidth'] = linewidth
        currentAxis = plt.gca()
        currentAxis.add_patch(Ellipse((x, y), w, h, **args))
        if fname is not None:
            plt.savefig(fname)
        if clear:
            plt.cla()

    def patch_rectangle(self, x, y, w=3, h=3, angle=0,
                        color='#6AA121', fill=False, clear=True,
                        linewidth=None, linestype='dashed',
                        fname='./patch_rectangle.png'):
        """Patch a rectangle to the existing panel

        @param x: the starting point of x axis
        @param y: the starting point of y axis

        Keyword arguments:
        w         -- width of the rectangle (default: 3)
        h         -- height of the rectangle (default: 3)
        angle     -- rotation angle of the rectangle (default: 0)
        color     -- rectangle color (default: #6AA121)
        fill      -- true to fill the rectangle (defaule: False)
        clear     -- true to clear panel after output (default: True)
        linewidth -- width of the edge line
        linestype -- style of the edge, solid, dashed (default),
                     dashdot, dotted
        title     -- chart title (default: '')
        fname     -- output filename (default: './points.png')

        """
        from matplotlib.patches import Rectangle
        args = {'edgecolor': color,
                'linestyle': linestype}
        if fill:
            args['facecolor'] = color
            args['linestyle'] = 'solid'
        else:
            args['facecolor'] = 'none'
        if linewidth is not None:
            args['linewidth'] = linewidth
        currentAxis = plt.gca()
        currentAxis.add_patch(Rectangle((x, y), w, h, **args))
        if fname is not None:
            plt.savefig(fname)
        if clear:
            plt.cla()

    def patch_rectangle_img(self, img_path, pos, new_name=None):
        """Open an image and patch a rectangle to it

        @param img_path: path of the image
        @param pos: position list, [left, top, right, bottom]

        Keyword parameters:
        new_name -- path of the patched image
                    (default: ori_name.replace('.jpg', '_patch.jpg'))

        """
        import cv2
        img = cv2.imread(img_path)
        if new_name is None:
            new_name = img_path.replace('.jpg', '_patch.jpg')
            new_name = new_name.replace('png', '_patch.png')
        cv2.rectangle(img, (pos[0], pos[1]),
                      (pos[2], pos[3]), (0, 255, 0), 2)
        cv2.imwrite(new_name, img)

    def plot_pie(self, data, bfrac=False, shadow=False, clear=True,
                 title='Pie Chart', cg='pink', radius=1.1,
                 pie_labels=None, expl=None, fname='./pie.png'):
        """Draw a pie chart

        @param data: a list of input data (1D)

        Keyword arguments:
        bfrac      -- true if the input data already represents fractions
                      (default: False)
        shadow     -- add shadow to the chart (default: False)
        title      -- chart title (default: 'Pie Chart')
        cg         -- color group to be used (default: 'pink')
        radius     -- radius of the pie (default: 1.1)
        pie_labels -- labels of each components
                      (default: index of the elements)
        expl       -- index of the item to explode (default: None)
        fname     -- output filename (default: './pie.png')
        clear     -- true to clear panel after output (default: True)

        """

        data = self.conv_to_np(data)

        plt.figure(1, figsize=(6, 6))
        ax = plt.axes([0.1, 0.1, 0.8, 0.8])
        fracs = data if bfrac else self.get_perc(data)
        if pie_labels is None:
            pie_labels = list(map(str, range(1, len(data)+1)))
        color_class = getattr(self, cg)

        args = {'labels': pie_labels,
                'autopct': '%1.1f%%',
                'shadow': shadow,
                'radius': radius,
                'textprops': {'color': color_class[0]},
                'startangle': 90,
                'colors': color_class[-len(data):]}

        if expl is not None:
            explode = [0]*len(data)
            explode[expl] = 0.05
            args['explode'] = explode

        plt.pie(fracs, **args)
        plt.title(title, color='#504A4B', weight='bold')
        if fname is not None:
            plt.savefig(fname)
        if clear:
            plt.cla()

    def plot_stacked_bar(self, data, xticks=None, xlabel='', legend=None,
                         ylabel='', xrotation=45, width=0.6, clear=True,
                         cg='blue', title='Stacked Bar Chart',
                         log=False, fname='stack_bar.png'):
        """Draw a bar chart with errors

        @param data: a list of input data (2D)

        Keyword arguments:
        xticks    -- ticks of the x axis (default: array index of the elements)
        xlabel    -- label of the X axis (default: '')
        legend    -- a list of the legend, must match len(data)
                     (default: index of the list to be drawn)
        ylabel    -- label of the y axis (default: '')
        xrotation -- rotation angle of xticks (default: 45)
        width     -- relative width of the bar (default: 0.6)
        cg        -- color group to be used (default: 'blue')
        title     -- chart title (default: 'Stacked Bar Chart')
        log       -- true to draw log scale (default: False)
        fname     -- output filename (default: './stack_bar.png')
        clear     -- true to clear panel after output (default: True)

        """
        _len = self.check_array_length(data)
        data = self.conv_to_np(data)

        ind = np.arange(_len)
        stack_colors = getattr(self, cg)
        if xticks is None:
            xticks = list(map(str, range(1, _len+1)))

        ymax = 0
        ymin = 0
        sum_array = np.zeros(_len)
        for i in range(0, len(data)):
            a = np.array(data[i]) if type(data[i]) is list else data[i]
            label = legend[i] if legend is not None else str(i)
            p = plt.bar(ind, a, width, bottom=sum_array,
                        log=log, label=label,
                        color=stack_colors[i % 10])
            sum_array = np.add(sum_array, a)
            _ymax, _ymin = self.find_axis_max_min(a)
            ymax += _ymax

        plt.axis([0, _len, ymin, ymax])
        plt.ylabel(ylabel, color='#504A4B')
        plt.xlabel(xlabel, color='#504A4B')
        plt.title(title, color='#504A4B', weight='bold')
        plt.xticks(ind + width/2., xticks)
        plt.legend(bbox_to_anchor=(1.12, 1.12), loc=1, borderaxespad=0.)
        if fname is not None:
            plt.savefig(fname)
        if clear:
            plt.cla()

    def plot_single_bar(self, data, xticks=None, xlabel='',
                        ylabel='', err=None, xrotation=45, clear=True,
                        width=0.6, color='#FFCCCC', title='Bar Chart',
                        log=False, fname='bar.png', ecolor='#009966'):
        """Draw a bar chart with errors

        @param data: a list of input data (1D)

        Keyword arguments:
        xticks    -- ticks of the x axis (default: array index of the elements)
        xlabel    -- label of the X axis (default: '')
        ylabel    -- label of the y axis (default: '')
        err       -- upper error array (default: None)
        xrotation -- rotation angle of xticks (default: 45)
        clear     -- true to clear panel after output (default: True)
        width     -- relative width of the bar (default: 0.6)
        color     -- color of the points (default: '#FFCCCC')
        title     -- chart title (default: 'Bar Chart')
        log       -- true to draw log scale (default: False)
        fname     -- output filename (default: './points.png')
        ecolor    -- color of the errors (default: '#00CCFF')

        """

        data = self.conv_to_np(data)
        if xticks is None:
            xticks = list(map(str, range(1, len(data)+1)))

        args = {'color': color, 'ecolor': ecolor}
        if err is not None:
            args['yerr'] = err

        ind = np.arange(len(xticks))
        rects1 = self.ax.bar(ind, data, width, **args)

        plt.title(title, color='#504A4B', weight='bold')
        self.ax.set_ylabel(ylabel, color='#504A4B')
        self.ax.set_xlabel(xlabel, color='#504A4B')
        self.ax.set_xticks(ind+width/2)
        self.ax.set_xticklabels(xticks, rotation=xrotation)
        if log:
            self.ax.set_yscale('log')
        if fname is not None:
            plt.savefig(fname)
        if clear:
            plt.cla()

    def plot_2D_dists(self, data, scale=False, legend=None, clear=True,
                      title='Distrubitions', connected=True, amin=None,
                      amax=None, xlabel='Index', ylabel='',
                      fname='./dist_2d.png'):
        """Draw the dist of multiple 2D arrays.

        @param data: list of 2D arrays

        Keyword arguments:
        scale     -- true to scale the distributions (default: False)
        legend    -- a list of the legend, must match len(data)
                     (default: index of the list to be drawn)
        xlabel    -- label of the X axis (default: 'Index')
        ylabel    -- label of the y axis (default: '')
        clear     -- true to clear panel after output (default: True)
        title     -- chart title (default: 'Distributions')
        amax      -- maximum of y axis (default: max(data)+0.1)
        amin      -- minimum of y axis (default: max(data)-0.1)
        connected -- true to draw line between dots (default: True)
        fname     -- output filename (default: './dist_2d.png')

        """
        _len = self.check_array_length(data)
        data = self.conv_to_np(data)

        ymax = amax
        ymin = amin
        xmax = None
        xmin = None
        fmt = '-o' if connected else 'o'
        for i in range(0, len(data)):
            label = legend[i] if legend is not None else str(i)
            a = data[i]
            if type(a) is list:
                a = np.array(a)
            if scale:
                a = self.scale(a)
            plt.plot(a[0], a[1], fmt, label=label)

            _xmax, _xmin = self.find_axis_max_min(a[0])
            _ymax, _ymin = self.find_axis_max_min(a[1])
            xmax = _xmax if xmax is None else max(xmax, _xmax)
            xmin = _xmin if xmin is None else min(xmin, _xmin)
            if amax is None:
                ymax = _ymax if ymax is None else max(ymax, _ymax)
            if amin is None:
                ymin = _ymin if ymin is None else min(ymin, _ymin)

        plt.axis([xmin, xmax, ymin, ymax])
        plt.title(title, color='#504A4B', weight='bold')
        plt.xlabel(xlabel, color='#504A4B')
        plt.ylabel(ylabel, color='#504A4B')
        plt.legend(bbox_to_anchor=(1.12, 1.0), loc=1, borderaxespad=0.)
        if fname is not None:
            plt.savefig(fname)
        if clear:
            plt.cla()

    def plot_1D_dists(self, data, scale=False, legend=None, clear=True,
                      title='Distrubitions', connected=True, amax=None,
                      amin=None, xlabel='Index', ylabel='',
                      fname='./dist_1d.png'):
        """Draw the dist of multiple 1D arrays.

        @param data: list of 1D arrays

        Keyword arguments:
        scale     -- true to scale the distributions (default: False)
        legend    -- a list of the legend, must match len(data)
                     (default: index of the list to be drawn)
        clear     -- true to clear panel after output (default: True)
        xlabel    -- label of the X axis (default: 'Index')
        ylabel    -- label of the y axis (default: '')
        title     -- chart title (default: 'Distributions')
        connected -- true to draw line between dots (default: True)
        amax      -- maximum of y axis (default: max(data)+0.1)
        amin      -- minimum of y axis (default: max(data)-0.1)
        fname     -- output filename (default: './dist_1d.png')

        """

        data = self.conv_to_np(data)

        ymax = amax
        ymin = amin
        xmax = None
        fmt = '-o' if connected else 'o'
        for i in range(0, len(data)):
            label = legend[i] if legend is not None else str(i)
            a = data[i]
            if type(a) is list:
                a = np.array(a)
            if scale:
                a = self.scale(a)
            plt.plot(a, fmt, label=label)

            _ymax, _ymin = self.find_axis_max_min(a)
            _xmax = 1.1*(len(a)-1)
            if amax is None:
                ymax = _ymax if ymax is None else max(ymax, _ymax)
            if amin is None:
                ymin = _ymin if ymin is None else min(ymin, _ymin)
            xmax = _xmax if xmax is None else max(xmax, _xmax)

        plt.axis([-0.1, xmax, ymin, ymax])
        plt.title(title, color='#504A4B', weight='bold')
        plt.xlabel(xlabel, color='#504A4B')
        plt.ylabel(ylabel, color='#504A4B')
        plt.legend(bbox_to_anchor=(1.12, 1.0), loc=1, borderaxespad=0.)
        if fname is not None:
            plt.savefig(fname)
        if clear:
            plt.cla()

    def histogram(self, data, xlabel='', ylabel='', clear=True,
                  title='Histogram', nbins=None, bfit=False,
                  fname='./hist.png', grid=True,
                  align='mid', log=False, facecolor='#339966'):
        """Draw histogram of the numpy array

        @param data: input array (1D)

        Keyword arguments:
        xlabel -- label of the X axis (default: '')
        ylabel -- label of the y axis (default: '')
        clear     -- true to clear panel after output (default: True)
        title  -- chart title (default: 'Histogram')
        nbins  -- number of bins (default: length of the set of input data)
        bfit   -- also draw fit function (default: False)
        fname  -- output filename (default: './hist.png')
        grid   -- draw grid (default: True)
        align  -- histogram alignment, mid, left, right (default: mid)
        log    -- true to draw log scale (default: False)
        facecolor -- color of the histogram (Default: #339966)

        """
        data = self.conv_to_np(data)

        if nbins is None:
            nbins = len(set(data))
        y, x, patches = plt.hist(data, nbins, normed=1, log=log,
                                 facecolor=facecolor, alpha=0.5,
                                 align=align, rwidth=1.0)
        if bfit:
            mu = np.mean(data)
            sigma = np.std(data)
            fit = mlab.normpdf(x, mu, sigma)
            plt.plot(x, fit, 'r--')

        plt.title(title, color='#504A4B', weight='bold')
        plt.ylabel(ylabel, color='#504A4B')
        plt.xlabel(xlabel, color='#504A4B')
        plt.grid(grid)
        xmax, xmin = self.find_axis_max_min(x)
        ymax, ymin = self.find_axis_max_min(y)
        plt.axis([xmin, xmax, 0, ymax])
        if fname is not None:
            plt.savefig(fname)
        if clear:
            plt.cla()

    def plot_points(self, x, y, err=None, err_low=None, clear=True,
                    connected=False, xlabel='', ylabel='', xticks=None,
                    fname='./points.png', title='', ymax=None, ymin=None,
                    ecolor='#3399FF', color='#CC6600'):
        """Plot points with (asymmetry) errors

        @param x: x array
        @param y: y array

        Keyword arguments:
        err       -- upper error array (default: None)
        err_low   -- lower error array (default: None or err if err is set)
        connected -- true to draw line between dots (default: False)
        xlabel    -- label of the X axis (default: '')
        ylabel    -- label of the y axis (default: '')
        clear     -- true to clear panel after output (default: True)
        title     -- chart title (default: '')
        fname     -- output filename (default: './points.png')
        ymax      -- maximum of y axis (default: max(data)+0.1)
        ymin      -- minimum of y axis (default: max(data)-0.1)
        ecolor    -- color of the errors (default: '#3399FF')
        color     -- color of the points (default: '#CC6600')

        """
        x = self.conv_to_np(x)
        y = self.conv_to_np(y)

        fmt = '-o' if connected else 'o'
        args = {'fmt': fmt, 'ecolor': ecolor, 'color': color}
        if err is not None:
            if err_low is not None:
                args['yerr'] = [err_low, err]
            else:
                args['yerr'] = [err, err]
        self.ax.errorbar(x, y, **args)
        self.ax.set_title(title)
        xmax, xmin = self.find_axis_max_min(x)
        plt.xlim(xmin, xmax)
        _ymax, _ymin = self.find_axis_max_min(y)
        if ymax is None:
            ymax = _ymax
        if ymin is None:
            ymin = _ymin
        plt.ylim(ymin, ymax)
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel(ylabel)
        if xticks is not None:
            xtick_marks = np.arange(len(x))
            plt.xticks(xtick_marks, xticks, rotation=45)
        if fname is not None:
            plt.savefig(fname)
        if clear:
            plt.cla()

    def plot_bubble_chart(self, x, y, z=None, scaler=1,
                          ascale_min=0.5, ascale_max=0.5,
                          xticks=None, xlabel='Bubble Chart',
                          clear=True, title='Bubble Chart',
                          ylabel='', fname='./bubble.png'):
        """Plot bubble chart

        @param x: x array
        @param y: y array

        Keyword arguments:
        z      -- z array to determine the size of bubbles (default [3]*N)
        scaler -- used for scaling the area (default: 1)
        ascale_min -- used for scaling x axis (default: 0.5)
        ascale_max -- used for scaling x axis (default: 0.5)
        title  -- chart title (default: 'Bubble Chart')
        xlabel -- label of the X axis (default 'Bubble Chart')
        ylabel -- label of the y axis (default '')
        fname  -- output filename (default './bubble.png')
        clear  -- true to clear panel after output (default: True)

        """
        N = len(x)
        x = self.conv_to_np(x)
        y = self.conv_to_np(y)
        colors = np.random.rand(N)
        if z is None:
            z = np.array([3]*N)
        elif type(z) is list:
            z = np.array(z)

        area = np.pi * (scaler * z)**2
        plt.scatter(x, y, s=area, c=colors, alpha=0.5)
        plt.ylabel(ylabel)
        plt.xlabel(xlabel)
        xlim = plt.xlim()
        plt.xlim(xlim[0]*ascale_min, xlim[1]*ascale_max)
        if xticks is not None:
            xtick_marks = np.arange(N)
            plt.xticks(xtick_marks, xticks, rotation=45)
        if fname is not None:
            plt.savefig(fname)
        if clear:
            plt.cla()

    def plot_confusion_matrix(self, cm, title='Confusion matrix',
                              xticks=None, yticks=None, fname='./cm.png',
                              xlabel='Predicted label',
                              ylabel='True label',
                              xrotation=45,
                              show_axis=True,
                              show_text=True, clear=True,
                              cmap=plt.cm.Blues, norm=True):

        self.plot_matrix(cm, title=title, xticks=xticks, yticks=yticks,
                         fname=fname, xlabel=xlabel, ylabel=ylabel,
                         xrotation=xrotation, show_text=show_text,
                         cmap=cmap, norm=norm, clear=clear,
                         show_axis=show_axis)

    def plot_matrix(self, cm, title='',
                    xticks=None, yticks=None, fname='./cm.png',
                    xlabel='Predicted label',
                    ylabel='True label',
                    xrotation=45, clear=True,
                    show_text=True,
                    show_axis=True,
                    cmap=plt.cm.Blues, norm=True):
        """Plot (confusion) matrix

        @param cm: input matrix

        Keyword arguments:
        title      -- chart title (default: '')
        xticks     -- ticks of the x axis (default: array index)
        yticks     -- ticks of the y axis (default: array index)
        fname      -- output filename (default: './cm.png')
        xlabel     -- label of the X axis (default: 'Predicted label')
        ylabel     -- label of the y axis (default: 'True label')
        xrotation  -- rotation angle of xticks (default: 45)
        clear      -- true to clear panel after output (default: True)
        show_text  -- true to show values on grids (default: True)
        show_axis  -- true to show axis (default: True)
        cmap       -- color map (defaul: Blues)
        norm       -- true to normlize numbers (default: True)

        """
        cm = self.conv_to_np(cm)
        if norm:
            cm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]

        plt.imshow(cm, interpolation='nearest', cmap=cmap)

        if show_text:
            diff = 1
            ind_array_x = np.arange(0, len(cm[0]), diff)
            ind_array_y = np.arange(0, len(cm), diff)
            x, y = np.meshgrid(ind_array_x, ind_array_y)
            for x_val, y_val in zip(x.flatten(), y.flatten()):
                c = round(cm[y_val][x_val], 2)
                self.ax.text(x_val, y_val, c, va='center', ha='center')

        plt.title(title, color='#504A4B', weight='bold')
        plt.colorbar()
        xtick_marks = np.arange(len(cm[0]))
        ytick_marks = np.arange(len(cm))
        if xticks is None:
            xticks = xtick_marks
        if yticks is None:
            yticks = ytick_marks
        plt.xticks(xtick_marks, xticks, rotation=xrotation)
        plt.yticks(ytick_marks, yticks)
        if len(xticks) > 20 or len(yticks) > 20:
            plt.locator_params(nbins=20)
        plt.tight_layout()
        plt.ylabel(ylabel, color='#504A4B')
        plt.xlabel(xlabel, color='#504A4B')
        if not show_axis:
            plt.axis('off')
        if fname is not None:
            plt.savefig(fname)
        if clear:
            plt.cla()
