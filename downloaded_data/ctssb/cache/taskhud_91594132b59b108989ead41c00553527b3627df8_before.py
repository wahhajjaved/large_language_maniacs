""" ---------------------------------------------------------------------------

    cwrapper.py - Implementation for CursesHud class

    Copyright 2017, John Ferguson

    Licensed under GPLv3, see LICENSE for full details

--------------------------------------------------------------------------- """

import curses

class CursesHud:
    """
    Object that accepts dictionaries representing data records.

    Records are parsed dynamically, so there's no need to configure column
    names ahead of time. Columns can be removed from display, and moved to
    the extended info panel at the bottom by calling set_extra_info().

    To modify record values, translating them to user readable values, call
    set_translation().

    Column widths are initially set to the size of the largest record value's
    length (or the column heading if longer). If the total of displayed column
    widths exceeds available columns in the terminal, 1 column width is
    subtracted from the largest column iteratively until all columns will fit.

    Any column headings/values which are truncated are suffixed by "..."
    """
    def __init__(self, screen):
        """
        screen: curses screen object
        """
        # ncurses screen object
        self.screen = screen
        self.screen.nodelay(True)   # self.screen.getch(), non-blocking

        # Column titles (keys in self.records)
        self.columns = []

        # keys in self.records that should be displayed in bottom pane
        self.extra_info_keys = []

        # Records to display in centre pane
        self.records = []

        # keys - key name from records
        # values - function accepting record value, returns string
        # Used to generically convert from data format to display format
        self.translations = {}

        # index in self.records that centre pane items start listing from
        self.scrollpos = 0

        # index from 0 of displayed items in centre pane that user has
        # selected with arrow keys
        self.selectpos = 0

        # height of bottom panel (for extended info display)
        self.bottom_panel_height = 4

    def set_extra_info(self, key):
        """
        set a key in records to be displayed in bottom panel rather than
        main display
        """
        if key in self.columns:
            self.columns.remove(key)
            self.extra_info_keys += [key]

    def set_translation(self, key, func):
        """
        Set callback which translates raw record values keyed by `key` by
        passing the raw value to `func`, which yields the display formatted
        string.
        """
        self.translations[key] = func

    def render(self):
        # TODO: need to apply translation to raw values
        # TODO: break this out into separate function, main panel as well
        # Render bottom panel first
        self.screen.addstr(curses.LINES - self.bottom_panel_height, 0, "─" * curses.COLS)
        for i in range(curses.LINES - self.bottom_panel_height + 1, curses.LINES):
            self.screen.addstr(i, 0, " " * (curses.COLS - 1))

        active_index = self.selectpos
        active_record = self.records[active_index]

        col_acc = 0
        line_acc = 0
        for field in self.extra_info_keys:
            if field not in active_record:
                continue

            st = "{}: {}, ".format(field, active_record[field])
            if col_acc + len(st) >= curses.COLS:
                col_acc = 0
                line_acc += 1

            self.screen.addstr(curses.LINES - self.bottom_panel_height + 1 + line_acc, col_acc, st)
            col_acc += len(st)


        #----------------------------------------------------------------------

        # Then, render the main view

        # TODO: this would be more efficient as a dict
        column_widths = []

        # Calculate widths for columns
        # TODO: cache these values if records don't change between renders
        for column in self.columns:
            record_max_width = 0

            for record in self.records:
                if column in record:
                    r_value = record[column]
                    if column in self.translations:
                        r_value = self.translations[column](r_value)
                    else:
                        r_value = str(r_value)
                    
                    record_max_width = max(record_max_width, len(r_value))

            record_max_width += 3

            # len(column) + 3:
            #   len(column): space for column header
            #   +2: left border + space
            #   +1: space on right of header
            column_widths += [max(record_max_width, len(column) + 3)]

        # Shrink columns until all fits on screen
        # TODO: handling when there's too many columns to render happily
        if sum(column_widths) >= curses.COLS:
            while sum(column_widths) >= (curses.COLS):
                idx_largest = column_widths.index(max(column_widths))
                column_widths[idx_largest] -= 1

        # draw column headings
        for n, column in enumerate(self.columns):
            col_start = sum(column_widths[0:n])
            col_width = column_widths[n]
            self.screen.addstr(0, col_start, "│")
            string = column
            truncated = string if len(string) < (column_widths[n] - 2) else string[:column_widths[n] - 6] + "..."
            self.screen.addstr(0, col_start + 2, truncated)
            self.screen.addstr(1, col_start, "┴" + ("─" * (col_width - 1)) )

            # Debug: show column widths with marker
            #self.screen.addstr(2 + (n % 2), col_start, "x" * col_width)
        # add left and right edge of column headings
        self.screen.addstr(1, 0, "└")
        self.screen.addstr(0, sum(column_widths), "│")
        self.screen.addstr(1, sum(column_widths), "┘")

        # display records
        slice_start = self.scrollpos
        slice_end = self.scrollpos + curses.LINES - 2 - self.bottom_panel_height
        record_slice = self.records[slice_start:slice_end]
        for nr, record in enumerate(record_slice):
            attr = 0

            if nr + slice_start == self.selectpos:
                attr = curses.A_REVERSE
            else:
                attr = curses.A_NORMAL
            self.screen.addstr(2+nr, 0, " " * (curses.COLS - 1), attr)

            for n, column in enumerate(self.columns):
                if column not in record:
                    continue

                col_start = sum(column_widths[0:n])

                value = record[column]
                if column in self.translations:
                    value = self.translations[column](value)

                string = str(value)
                truncated = string if len(string) < (column_widths[n] - 2) else string[:column_widths[n] - 6] + "..."
                self.screen.addstr(2 + nr, col_start + 2, truncated, attr)

        # draw latest changes to screen
        self.screen.refresh()

    def add_column(self, name):
        """
        Add a column to the HUD
        """
        self.columns += [name]

    def add_record(self, records):
        """
        add records to the display, will add columns as needed. `record` is
        a dictionary, or a list of dictionaries.
        """
        if type(records) is not list:
            records = [records]

        for record in records:
            # If record already exists, skip it
            if record in self.records:
                continue

            # TODO: need hook to remove columns when no records in the database
            #       have those keys
            # see if new columns are needed to support this record
            for k in record.keys():
                if k not in self.columns:
                    self.add_column(k)

            # add record to local store
            self.records += [record]

    def mainloop(self):
        """
        Called after HUD has been set up. Handles rendering and user input.
        """
        # Disable cursor display by default
        curses.curs_set(0)

        # Display initial state
        self.render()

        while True:
            # Render before fetching input
            self.render()

            # note: call is non-blocking, per __init__ calling nodelay(True)
            c = self.screen.getch()

            if c == curses.KEY_RESIZE:
                # Terminal has been resized

                # must be called so that curses.LINES, curses.COLS will change
                curses.update_lines_cols()

                # in case old data won't be redrawn after resize
                self.screen.clear()

            if c == curses.KEY_UP:
                # Move up as far as the 0th record
                self.selectpos = max(self.selectpos - 1, 0)
                if self.selectpos < self.scrollpos:
                    # Handle scrolling if we were at the first record on screen
                    self.scrollpos -= 1
                    
            if c == curses.KEY_DOWN:
                # Move down as far as the Nth record
                self.selectpos = min(self.selectpos + 1, len(self.records) - 1)
                if self.selectpos >= (self.scrollpos + curses.LINES - 2 - self.bottom_panel_height) :
                    # Handle scrolling if we were at the last record on screen
                    self.scrollpos += 1

