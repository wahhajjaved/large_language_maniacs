import curses
import time

class CursesHud:
    def __init__(self, screen):
        """
        screen: curses screen object
        """
        self.screen = screen
        self.screen.nodelay(True)

        self.columns = []
        self.extra_info_keys = []
        self.records = []

        self.scrollpos = 0
        self.selectpos = 0

    def set_extra_info(self, key):
        """
        set a key in records to be displayed in bottom panel rather than
        main display
        """
        if key in self.columns:
            self.columns.remove(key)
            self.extra_info_keys += [key]

    def render(self):
        column_widths = []

        # Calculate widths for columns
        # TODO: cache these values if records don't change between renders
        for column in self.columns:
            record_max_width = 0

            for record in self.records:
                if column in record:
                    record_max_width = max(record_max_width, len(str(record[column])))

            record_max_width += 3

            # len(column) + 3:
            #   len(column): space for column header
            #   +2: left border + space
            #   +1: space on right of header
            column_widths += [max(record_max_width, len(column) + 3)]

        # Shrink columns until all fits on screen
        # TODO: handling when there's too many columns to render happily
        if sum(column_widths) > curses.COLS:
            while sum(column_widths) > (curses.COLS - 1):
                idx_largest = column_widths.index(max(column_widths))
                column_widths[idx_largest] -= 1

        # draw column headings
        for n, column in enumerate(self.columns):
            col_start = sum(column_widths[0:n])
            col_width = column_widths[n]
            self.screen.addstr(0, col_start, "│")
            string = column
            truncated = string if len(string) < column_widths[n] - 3 else string[:column_widths[n] - 6] + "..."
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
        slice_end = self.scrollpos + curses.LINES - 2
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
                string = str(record[column])
                truncated = string if len(string) < column_widths[n] else string[:column_widths[n] - 6] + "..."
                self.screen.addstr(2 + nr, col_start + 2, truncated, attr)

        self.screen.refresh()

    def add_column(self, name):
        """
        Add a column to the HUD
        """
        self.columns += [name]

    def add_record(self, record):
        """
        add a record to the display, will add columns as needed. `record` is
        a dictionary
        """
        # see if new columns are needed to support this record
        for k in record.keys():
            if k not in self.columns:
                self.add_column(k)

        self.records += [record]


    def mainloop(self):
        curses.curs_set(0)
        self.render()

        self.x = 0
        
        while True:
            self.render()

            c = self.screen.getch()

            if c == curses.KEY_RESIZE:
                curses.update_lines_cols()
                self.screen.clear()
                self.render()
            if c == curses.KEY_UP:
                self.selectpos = max(self.selectpos - 1, 0)
                if self.selectpos < self.scrollpos:
                    self.scrollpos -= 1
                    
            if c == curses.KEY_DOWN:
                self.selectpos = min(self.selectpos + 1, len(self.records) - 1)
                if self.selectpos >= (self.scrollpos + curses.LINES - 2) :
                    self.scrollpos += 1
