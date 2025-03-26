"""
IPython/Jupyter Notebook progressbar decorator for iterators.
Includes a default (x)range iterator printing to stderr.

Usage:
  >>> from tqdm_notebook import tnrange[, tqdm_notebook]
  >>> for i in tnrange(10): #same as: for i in tqdm_notebook(xrange(10))
  ...     ...
"""
# future division is important to divide integers and get as
# a result precise floating numbers (instead of truncated int)
from __future__ import division, absolute_import
# import compatibility functions and utilities
import sys
from ._utils import _range

# import IPython/Jupyter base widget and display utilities
try:  # pragma: no cover
    # For IPython 4.x using ipywidgets
    from ipywidgets import IntProgress, HBox, HTML
except ImportError:  # pragma: no cover
    try:  # pragma: no cover
        # For IPython 3.x
        from IPython.html.widgets import IntProgress, HBox, HTML
    except ImportError:  # pragma: no cover
        try:  # pragma: no cover
            # For IPython 2.x
            from IPython.html.widgets import IntProgressWidget as IntProgress
            from IPython.html.widgets import ContainerWidget as HBox
            from IPython.html.widgets import HTML
        except ImportError:  # pragma: no cover
            pass
try:  # pragma: no cover
    from IPython.display import display  # , clear_output
except ImportError:  # pragma: no cover
    pass

# HTML encoding
try:  # pragma: no cover
    from html import escape  # python 3.x
except ImportError:  # pragma: no cover
    from cgi import escape  # python 2.x

# to inherit from the tqdm class
from ._tqdm import tqdm


__author__ = {"github.com/": ["lrq3000", "casperdcl"]}
__all__ = ['tqdm_notebook', 'tnrange']


class tqdm_notebook(tqdm):  # pragma: no cover
    """
    Experimental IPython/Jupyter Notebook widget using tqdm!
    """

    @staticmethod
    def status_printer(file, total=None, desc=None):
        """
        Manage the printing of an IPython/Jupyter Notebook progress bar widget.
        """
        # Fallback to text bar if there's no total
        if not total:
            return super(tqdm_notebook, tqdm_notebook).status_printer(file)

        fp = file
        if not getattr(fp, 'flush', False):  # pragma: no cover
            fp.flush = lambda: None

        # Prepare IPython progress bar
        pbar = IntProgress(min=0, max=total)
        if desc:
            pbar.description = desc
        # Prepare status text
        ptext = HTML()
        # Only way to place text to the right of the bar is to use a container
        container = HBox(children=[pbar, ptext])
        display(container)

        def print_status(s='', close=False, bar_style=None):
            # Clear previous output (really necessary?)
            # clear_output(wait=1)

            # Get current iteration value from format_meter string
            n = None
            if s:
                npos = s.find(r'/|/')  # because we use bar_format=r'{n}|...'
                # Check that n can be found in s (else n > total)
                if npos >= 0:
                    n = int(s[:npos])  # get n from string
                    s = s[npos+3:]  # remove from string

                    # Update bar with current n value
                    if n is not None:
                        pbar.value = n

            # Print stats
            s = s.replace('||', '')  # remove inesthetical pipes
            s = escape(s)  # html escape special characters (like '?')
            ptext.value = s

            if bar_style:
                # Hack-ish way to avoid the danger bar_style being overriden by success because the bar gets closed after the error...
                if pbar.bar_style != 'danger' and bar_style != 'success':
                    pbar.bar_style = bar_style

            # Special signal to close the bar
            if close:
                container.visible = False

        return print_status

    def __init__(self, *args, **kwargs):
        # Setup default output
        if not kwargs.get('file', None) or kwargs['file'] == sys.stderr:
            kwargs['file'] = sys.stdout  # avoid the red block in IPython

        # Remove the bar from the printed string, only print stats
        if not kwargs.get('bar_format', None):
            kwargs['bar_format'] = r'{n}/|/{l_bar}{r_bar}'

        super(tqdm_notebook, self).__init__(*args, **kwargs)

        # Delete the text progress bar display
        self.sp('')
        # Replace with IPython progress bar display
        self.sp = self.status_printer(self.fp, self.total, self.desc)
        self.desc = None  # trick to place description before the bar

        # Print initial bar state
        if not self.disable:
            # TODO: replace by self.refresh()
            self.sp(self.format_meter(self.n, self.total, 0,
                    (self.dynamic_ncols(self.file) if self.dynamic_ncols
                     else self.ncols),
                    self.desc, self.ascii, self.unit, self.unit_scale, None,
                    self.bar_format))

    def __iter__(self, *args, **kwargs):
        try:
            for obj in super(tqdm_notebook, self).__iter__(*args, **kwargs):
                yield obj  # cannot just return super(tqdm...) because can't catch exception
        except:  # DO NOT use except as, or even except Exception, it simply won't work with IPython async KeyboardInterrupt
            self.sp(bar_style='danger')
            raise

    def update(self, *args, **kwargs):
        try:
            super(tqdm_notebook, self).update(*args, **kwargs)
        except Exception as exc:
            # Note that we cannot catch KeyboardInterrupt when using manual tqdm
            # because the interrupt will most likely happen on another statement
            self.sp(bar_style='danger')
            raise exc

    def close(self, *args, **kwargs):
        super(tqdm_notebook, self).close(*args, **kwargs)
        if self.leave:
            self.sp(bar_style='success')
        else:
            self.sp(s='', close=True)

    def moveto(*args, **kwargs):
        # Nullify moveto to avoid outputting \n (blank lines) in the IPython output cell
        return


def tnrange(*args, **kwargs):  # pragma: no cover
    """
    A shortcut for tqdm_notebook(xrange(*args), **kwargs).
    On Python3+ range is used instead of xrange.
    """
    return tqdm_notebook(_range(*args), **kwargs)
