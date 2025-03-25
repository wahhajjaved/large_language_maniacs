#
# Copyright (C) 2008 Francesco Salvestrini
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

import sys
import textwrap

from   Debug         import *
from   Trace         import *
from   Command       import *
import Exceptions
import Color
import DB
import Tree
import Priority
import ID
from   Visitor       import *
from   Root          import *
from   Entry         import *
import Terminal
import Filter

class ShowVisitor(Visitor) :
    def __init__(self, colors, verbose, show_all, width, filter) :
        assert(type(width) == int)
        assert(filter != None)

        super(ShowVisitor, self).__init__()

        # XXX FIXME:
        #      We need to start from -1 in order to have 0 as id for the
        #      database name

        self.__width   = width
        self.__colors  = colors
        self.__verbose = verbose
        self.__all     = show_all
        self.__filter  = filter.function
        self.__cmap    = {
            Priority.Priority.PRIORITY_VERYHIGH : bright_red,
            Priority.Priority.PRIORITY_HIGH     : bright_yellow,
            Priority.Priority.PRIORITY_MEDIUM   : bright_white,
            Priority.Priority.PRIORITY_LOW      : normal_cyan,
            Priority.Priority.PRIORITY_VERYLOW  : normal_blue,
            }

    def visitEntry(self, e) :
        assert(e != None)

        if (not self.__filter(e)) :
            debug("Entry "                 +
                  "`" + str(e) + "' "      +
                  "does not match filter " +
                  "`" + str(self.__filter) + "'")
            return

        debug("Visiting entry " + str(e))

        # Handle colors
        if (self.__colors == True) :
            color_info  = normal_green
            color_index = normal_green
            p           = e.priority.value
            try :
                color_text  = self.__cmap[p]
            except KeyError :
                bug("Unknown key `" + p.tostring() + "'")
                color_text = white
        else :
            # A bunch of pass-through lambdas
            color_index = lambda x: x
            color_text  = lambda x: x
            color_info  = lambda x: x
        assert(color_index != None)
        assert(color_text  != None)
        assert(color_info  != None)

        # Build the output
        if ((not e.done()) or (e.done() and self.__all)) :
            if (e.done()) :
                mark = "-"
            else :
                mark = " "

            header = \
                self.indent()                        + \
                mark                                 + \
                color_index(str(self.index()) + ".")
            indent = " " * len(self.indent()                + \
                                   mark                     + \
                                   str(self.index()) + ".")

            if (self.__width == 0) :
                lines = [ e.text ]
            else :
                rows = self.__width - len(header)
                debug("Need to wrap text on " + str(rows) + " rows")
                if (rows <= 0) :
                    lines = [ "..." ]
                else :
                    lines = textwrap.wrap(e.text, rows)
            debug("Got " + str(len(lines)) + " lines to show")

            i = 0
            for line in lines :
                if (i == 0) :
                    print(header + color_text(line))
                else :
                    print(indent + color_text(line))
                i = i + 1

            if (self.__verbose) :
                l    = " " * (len(mark) + len(str(self.index())) + len("."))
                line1 = self.indent() + l

                line1 = line1 + color_info("Start:") + " "
                if (e.start != None) :
                    line1 = line1 + e.start.tostring()
                else :
                    line1 = line1 + "Unknown"
                line1 = line1 + " " + color_info("End:") + " "
                if (e.end != None) :
                    line1 = line1 + e.end.tostring()
                else :
                    line1 = line1 + "Unknown"

                line2 = self.indent() + l +         \
                    color_info("Priority:") + " " + \
                    e.priority.tostring() +         \
                    " " + color_info("Duration:") + " "
                if (e.end != None) :
                    d = e.end - e.start
                    line2 = line2 + d.tostring()
                else :
                    line2 = line2 + "Incomplete"

                print(line1)
                print(line2)
                print("")

    def visitRoot(self, r) :
        assert(r != None)

        debug("Visiting root " + str(r))

        if (self.__colors) :
            color_index = normal_green
            color_text = normal_white
        else :
            color_index = lambda x: x # pass-through
            color_text  = lambda x: x # pass-through

            assert(color_index != None)
            assert(color_text != None)

        print(self.indent()                 +
              color_index(str(self.index()) + ".") +
              color_text(r.text))

    def indent(self) :
        return " " * 2 * self.level_current()

class SubCommand(Command) :
    def __init__(self) :
        Command.__init__(self,
                         name   = "show",
                         footer = [
                "FILTER  " + Filter.help(),
                "ID      " + ID.help(),
                "WIDTH   An integer >= 0, 0 means no formatting"
                ])

    def short_help(self) :
        return "display node(s)"

    def authors(self) :
        return [ "Francesco Salvestrini" ]

    def do(self, configuration, arguments) :
        Command.add_option(self, "-a", "--all",
                           action = "store_true",
                           dest   = "all",
                           help   = "show all nodes")
        Command.add_option(self,
                           "-i", "--id",
                           action = "store",
                           type   = "string",
                           dest   = "id",
                           help   = "specify starting node")
        Command.add_option(self,
                           "-w", "--width",
                           action = "store",
                           type   = "string",
                           dest   = "width",
                           help   = "specify maximum text width")
        Command.add_option(self,
                           "-F", "--filter",
                           action = "store",
                           type   = "string",
                           dest   = "filter",
                           help   = "specify selection filter")

        (opts, args) = Command.parse_args(self, arguments)
        if (len(args) > 0) :
            raise Exceptions.UnknownParameter(args[0])

        # Parameters setup
        starting_id = opts.id
        if (starting_id == None) :
            starting_id = "0"
        node_id = ID.ID(starting_id)

        try :
            width = configuration.get(PROGRAM_NAME, 'width', raw = True)
        except :
            t     = Terminal.Terminal()
            width = t.columns
            debug("No width related configuration, default to " +
                  str(width))
        assert(width != None)

        if (opts.width != None) :
            width = int(opts.width)
        assert(type(width) == int)
        if (width < 0) :
            raise Exceptions.WrongParameter("width must be greater or equal "
                                            "than 0")
        assert(width >= 0)

        try :
            colors = configuration.get(PROGRAM_NAME, 'colors', raw = True)
        except :
            colors = False
            debug("No colors related configuration, default to " +
                  str(colors))
        assert(colors != None)

        try :
            verbose = configuration.get(PROGRAM_NAME, 'verbose', raw = True)
        except :
            verbose = False
            debug("No verboseness related configuration, default to " +
                  str(verbose))
        assert(verbose != None)

        # Build the filter
        filter_text = "all"
        if (opts.filter != None) :
            filter_text = opts.filter
        filter = Filter.Filter(filter_text)
        assert(filter != None)

        # Work

        # Load DB
        db_file = configuration.get(PROGRAM_NAME, 'database')
        assert(db_file != None)

        db   = DB.Database()
        tree = db.load(db_file)
        assert(tree != None)

        show_all = False
        if (opts.all == True) :
            show_all = True

        node = Tree.find(tree, node_id)
        if (node == None) :
            raise Exceptions.NodeUnavailable(str(node_id))

        v = ShowVisitor(colors, verbose, show_all, width, filter)
        node.accept(v)

        debug("Success")

# Test
if (__name__ == '__main__') :
    debug("Test completed")
    sys.exit(0)
