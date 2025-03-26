#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint:disable=unused-wildcard-import,wildcard-import,invalid-name
"""Controls used by the TKinter GUI."""
from __future__ import print_function, unicode_literals, absolute_import

import sys
import types

from . import binding

if sys.version_info[0] == 3:  # Alternate import names
    # pylint:disable=import-error
    from tkinter import *
    from tkinter.ttk import *
    import tkinter.simpledialog as simpledialog
    import tkinter.font as tkFont
else:
    # pylint:disable=import-error
    from Tkinter import *
    from ttk import *
    import tkSimpleDialog as simpledialog
    import tkFont

# Monkeypatch simpledialog to use themed dialogs from ttk
if sys.platform != 'darwin':  # OS X looks better without patch
    simpledialog.Toplevel = Toplevel
    simpledialog.Entry = Entry
    simpledialog.Frame = Frame
    simpledialog.Button = Button

# Make Enter on button with focus activate it
TtkButton = Button
#pylint: disable=too-many-public-methods
class Button(TtkButton):  # pylint:disable=function-redefined,missing-docstring
    def __init__(self, master=None, **kw):
        TtkButton.__init__(self, master, **kw)
        if 'command' in kw:
            self.bind('<Return>', lambda e: kw['command']())

# http://effbot.org/zone/tkinter-autoscrollbar.htm
class _AutoScrollbar(Scrollbar):
    """A scrollbar that hides itself if it's not needed."""
    # pylint:disable=arguments-differ
    def set(self, lo, hi):
        """Only show scrollbar when there's more content than will fit."""
        if (float(lo) <= 0.0 and float(hi) >= 1.0) or (
                hasattr(self, 'hidden') and self.hidden):
            self.grid_remove()
        else:
            self.grid()
        Scrollbar.set(self, lo, hi)

# http://www.voidspace.org.uk/python/weblog/arch_d7_2006_07_01.shtml#e387
class _ToolTip(object):
    """Tooltip widget."""
    def __init__(self, widget, text):
        self.widget = widget
        self.tipwindow = None
        self.id = None
        self.event = None
        self.text = text
        self.active = False

    def showtip(self):
        """Displays the tooltip."""
        self.active = True
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_pointerx() + 16
        y = self.widget.winfo_pointery() + 16
        self.tipwindow = tw = Toplevel(self.widget)
        tw.wm_overrideredirect(1)
        tw.wm_geometry("+%d+%d" % (x, y))
        try:
            # pylint:disable=protected-access
            # For OS X
            tw.tk.call(
                "::tk::unsupported::MacWindowStyle", "style", tw._w, "help",
                "noActivates")
        except TclError:
            pass
        label = Label(
            tw, text=self.text, justify=LEFT, background="#ffffe0",
            relief=SOLID, borderwidth=1)
        label.pack(ipadx=1)

    def hidetip(self):
        """Hides the tooltip."""
        tw = self.tipwindow
        self.tipwindow = None
        self.active = False
        if tw:
            tw.destroy()

    def settext(self, text):
        """
        Sets the tooltip text and redraws it if necessary.

        Params:
            text
                The new tooltip text.
        """
        if text == self.text:
            return
        self.text = text
        if self.active:
            self.hidetip()
            self.showtip()

_TOOLTIP_DELAY = 500

__ui = None

# pylint:disable=too-few-public-methods
class _FakeControl(object):
    """Fake control returned if an option doesn't exist."""
    # pylint:disable=unused-argument
    @staticmethod
    def grid(*args, **kwargs):
        """Prevents breaking for code that tries to layout the control."""
        return
    pack = grid

fake_control = _FakeControl()

def init(ui):
    """Connect to a TkGui instance."""
    # pylint:disable=global-statement
    global __ui
    __ui = ui

def create_tooltip(widget, text):
    """
    Creates and returns a tooltip for a widget.

    Params:
        widget
            The widget to associate the tooltip to.
        text
            The tooltip text.
    """
    tooltip = _ToolTip(widget, text)
    # pylint:disable=unused-argument
    def enter(event):
        """
        Event handler on mouse enter.

        Params:
            event
                The event data."""
        if tooltip.event:
            widget.after_cancel(tooltip.event)
        tooltip.event = widget.after(_TOOLTIP_DELAY, tooltip.showtip)

    def leave(event):
        """
        Event handler on mouse exit.

        Params:
            event
                The event data.
        """
        if tooltip.event is not None:
            widget.after_cancel(tooltip.event)
            tooltip.event = None
        tooltip.hidetip()
    widget.bind('<Enter>', enter)
    widget.bind('<Leave>', leave)
    return tooltip

def create_control_group(parent, text, dual_column=False):
    """
    Creates and returns a Frame or Labelframe to group controls.

    Params:
        text
            The caption for the Labelframe. If None, returns a Frame.
        dual_column
            If True, configures the frame for a dual-column grid layout.
    """
    f = None
    if text is not None:
        f = Labelframe(parent, text=text)
    else:
        f = Frame(parent)
    if dual_column:
        Grid.columnconfigure(f, 0, weight=1)
        Grid.columnconfigure(f, 1, weight=1)
    return f

def create_option_button(
        parent, text, tooltip, option, update_func=None):
    """
    Creates and returns a button bound to an option.

    Params:
        parent
            The parent control for the button.
        text
            The button text.
        tooltip
            The tooltip for the button.
        option
            The keyword used for the option.
        update_func
            If given, a reference to a function that pre-processes the
            given option for display.
    """
    return create_trigger_option_button(
        parent, text, tooltip, lambda: __ui.cycle_option(option), option,
        update_func)

def create_trigger_button(parent, text, tooltip, command):
    """
    Creates and returns a button that triggers an action when clicked.

    Params:
        parent
            The parent control for the button.
        text
            The button text.
        tooltip
            The tooltip for the button.
        command
            Reference to the function called when the button is clicked.
    """
    b = Button(parent, text=text, command=command)
    create_tooltip(b, tooltip)
    return b

#pylint: disable=too-many-arguments
def create_trigger_option_button(
        parent, text, tooltip, command, option, update_func=None):
    """
    Creates and returns a button bound to an option, with a special action
    triggered on click.

    Params:
        parent
            The parent control for the button.
        text
            The button text.
        tooltip
            The tooltip for the button.
        command
            Reference to the function called when the button is clicked.
        option
            The keyword used for the option.
        update_func
            If given, a reference to a function that pre-processes the
            given option for display.
    """
    if not binding.version_has_option(option):
        return fake_control
    b = create_trigger_button(parent, text, tooltip, command)
    binding.bind(b, option, update_func)
    return b

def create_scrollbar(parent, control, **gridargs):
    """
    Creates and layouts a vertical scrollbar associated to <control>.

    Params:
        parent
            The parent control for the scrollbar.
        control
            The control to attach the scrollbar to.
        gridargs
            Keyword arguments used to apply grid layout to the scrollbar.
    """
    s = _AutoScrollbar(parent, orient=VERTICAL, command=control.yview)
    control['yscrollcommand'] = s.set
    s.grid(sticky="ns", **gridargs)
    s.grid_remove()
    return s

def listbox_identify(listbox, y):
    """Returns the index of the listbox item at the supplied (relative) y
    coordinate"""
    item = listbox.nearest(y)
    if item != -1 and listbox.bbox(item)[1] + listbox.bbox(item)[3] > y:
        return item
    return None

def treeview_tag_set(tree, tag, item, state=True, toggle=False):
    """
    Adds or removes a tag from the Treeview item's tags. Returns True if
    tag is now set or False if it is not.

    Params:
        item
            Treeview item id
        state
            True to set the tag; False to remove the tag.
        toggle
            If set to True, will toggle the tag. Overrides on.
    """
    # This is necessary because tag_add and tag_remove are not in the Python
    # bindings for Tk, and this is more readable (and likely not any slower)
    # than using arcane tk.call() syntax
    tags = list(tree.item(item, 'tags'))
    is_set = tag in tags
    if toggle:
        state = not is_set

    if state and (not is_set):
        tags.append(tag)
    elif (not state) and is_set:
        tags.remove(tag)

    tree.item(item, tags=tags)
    return state

def create_file_list(parent, title, listvar, **args):
    """
        Creates a file list with a scrollbar. Returns a tuple
        (frame, listbox).

        Params:
            parent
                The parent control for the list.
            title
                The title for the frame.
            listvar
                The Variable containing the list items.
            args
                Additions keyword arguments for the file list itself.
    """
    if 'height' not in args:
        args['height'] = 4
    lf = create_control_group(parent, title)
    lf.pack(side=BOTTOM, fill=BOTH, expand=Y, anchor="s")
    Grid.columnconfigure(lf, 0, weight=2)
    Grid.rowconfigure(lf, 1, weight=1)
    lb = Listbox(
        lf, listvariable=listvar, activestyle='dotbox', exportselection=0,
        **args)
    lb.identify = types.MethodType(listbox_identify, lb)
    lb.grid(column=0, row=0, rowspan=2, sticky="nsew")
    create_scrollbar(lf, lb, column=1, row=0, rowspan=2)
    return (lf, lb)

def create_readonly_file_list_buttons(
        parent, title, listvar, load_fn, refresh_fn, **args):
    """
        Creates a file list with load and refresh buttons. Returns a tuple
        (frame, listbox, buttons).

        Params:
            parent
                The parent control for the list.
            title
                The title for the frame.
            listvar
                The Variable containing the list items.
            load_fn
                Reference to a function to be called when the Load button
                is clicked.
            refresh_fn
                Reference to a function to be called when the Refresh button
                is clicked.
            args
                Additions keyword arguments for the file list itself.
    """
    (lf, lb) = create_file_list(parent, title, listvar, **args)
    buttons = Frame(lf)
    load = create_trigger_button(buttons, 'Load', 'Load selected', load_fn)
    load.pack(side=TOP)
    refresh = create_trigger_button(
        buttons, 'Refresh', 'Refresh list', refresh_fn)
    refresh.pack(side=TOP)
    buttons.grid(column=2, row=0, sticky="n")
    return (lf, lb, buttons)

#pylint: disable=too-many-arguments
def create_file_list_buttons(
        parent, title, listvar, load_fn, refresh_fn, save_fn,
        delete_fn, **args):
    """
        Creates a file list with load, refresh, save and delete buttons.
        Returns a tuple (frame, listbox, buttons).

        Params:
            parent
                The parent control for the list.
            title
                The title for the frame.
            listvar
                The Variable containing the list items.
            load_fn
                Reference to a function to be called when the Load button
                is clicked.
            refresh_fn
                Reference to a function to be called when the Refresh button
                is clicked.
            save_fn
                Reference to a function to be called when the Save button
                is clicked.
            delete_fn
                Reference to a function to be called when the Delete button
                is clicked.
            args
                Additions keyword arguments for the file list itself.
    """
    (lf, lb, buttons) = create_readonly_file_list_buttons(
        parent, title, listvar, load_fn, refresh_fn, **args)
    save = create_trigger_button(buttons, 'Save', 'Save current', save_fn)
    save.pack(side=TOP)
    delete = create_trigger_button(
        buttons, 'Delete', 'Delete selected', delete_fn)
    delete.pack(side=TOP)
    return (lf, lb, buttons)

def add_default_to_entry(entry, default_text):
    """Adds bindings to entry such that when there is no user text in the
    entry, the entry will display default_text in grey and italics."""
    normal_font = tkFont.Font(font='TkDefaultFont')
    default_font = tkFont.Font(font='TkDefaultFont')
    default_font.config(slant=tkFont.ITALIC)
    entry.default_showing = True

    def focus_out(_): # pylint:disable=missing-docstring
        if len(entry.get()) == 0:
            entry.insert(0, default_text)
            entry.configure(font=default_font, foreground='grey')
            entry.default_showing = True

    def focus_in(_): # pylint:disable=missing-docstring
        if entry.default_showing:
            entry.delete(0, END)
            entry.configure(font=normal_font, foreground='black')
            entry.default_showing = False

    entry.bind('<FocusIn>', focus_in)
    entry.bind('<FocusOut>', focus_out)

    focus_out(0)

def create_list_with_entry(parent, title, listvar, buttonspec, **kwargs):
    """
    Creates a control group with a listbox, a text entry, and any number of
    buttons specified with buttonspec. Does not lay out the control group in
    its parent.
    Returns a tuple (frame, entry, lsitbox)

    Params:
        parent
            The parent control for the list.
        title
            The title for the frame.
        listvar
            The Variable containing the list items.
        buttonspec
            A list of tuples (title, tooltip, function) specifying the buttons
    """
    entry_default = kwargs.pop('entry_default', None)
    if 'height' not in kwargs:
        kwargs['height'] = 4

    kf = create_control_group(parent, title)
    kf.configure(pad=(2, 0, 2, 2))
    kf.columnconfigure(0, weight=1)
    kf.rowconfigure(2, weight=1)

    ke = Entry(kf) # text box
    ke.grid(row=1, column=0, sticky='ewn', pady=(1, 4))

    lf = Frame(kf) # Listbox and scrollbar
    kb = Listbox(lf, listvariable=listvar, activestyle='dotbox',
                 exportselection=0, **kwargs)
    lf.configure(borderwidth=kb['borderwidth'], relief=kb['relief'])
    kb.configure(borderwidth=0, relief='flat')
    kb.grid(row=0, column=0, sticky='nsew')
    create_scrollbar(lf, kb, row=0, column=1)
    lf.rowconfigure(0, weight=1)
    lf.columnconfigure(0, weight=1)
    lf.grid(row=2, column=0, rowspan=1, sticky='nsew')

    bf = Frame(kf) # buttons
    for i, bn in enumerate(buttonspec):
        pad = 0 if i == 0 else (5, 0)
        create_trigger_button(bf, *bn).grid(row=i, pady=pad)
    bf.grid(column=1, row=1, rowspan=2, sticky='ns', padx=(4, 0))

    if entry_default:
        add_default_to_entry(ke, entry_default)

    return (kf, ke, kb)

def create_toggle_list(parent, columns, framegridopts, listopts={}):
    """
    Creates and returns a two-column Treeview in a frame to show toggleable
    items in a list.

    Params:
        parent
            The parent control for the Treeview.
        columns
            Column data for the Treeview.
        framegridopts
            Additional options for grid layout of the frame.
        listopts
            Additional options for the Treeview.
    """
    # pylint:disable=star-args,dangerous-default-value
    lf = Frame(parent)
    lf.grid(**framegridopts)
    Grid.rowconfigure(lf, 0, weight=1)
    Grid.columnconfigure(lf, 0, weight=1)
    lst = Treeview(lf, columns=columns, show=['headings'], **listopts)
    lst.tag_set = types.MethodType(treeview_tag_set, lst)
    lst.grid(column=0, row=0, sticky="nsew")
    create_scrollbar(lf, lst, column=1, row=0)
    return lst

def create_numeric_entry(parent, variable, option, tooltip):
    """
    Creates and returns an Entry suitable for input of small, numeric values
    and hooks up notification of changes.

    Params:
        parent
            The parent control for the Entry.
        variable
            The StringVar used to store the value internally.
        option
            The keyword used for the option.
        tooltip
            The tooltip for the Entry.
    """
    if not binding.version_has_option(option):
        return fake_control
    e = Entry(
        parent, width=4, validate='key',
        validatecommand=__ui.vcmd, textvariable=variable)
    variable.trace(
        "w", lambda name, index, mode: __ui.change_entry(option, variable))
    create_tooltip(e, tooltip)
    binding.bind(e, option)
    return e

# vim:expandtab
