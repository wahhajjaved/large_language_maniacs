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

from   Debug         import *
from   Trace         import *
from   Command       import *
import Exceptions
from   Configuration import *
import DB
import Entry
from   ID            import *

def description() :
    return "initialize the database"

def do(configuration, arguments) :
    command = Command("init")
    command.add_option("-f", "--force",
                       action = "store_true",
                       dest   = "force",
                       help   = "force operation")

    (opts, args) = command.parse_args(arguments)

    # Parameters setup
    if (opts.force != True) :
        debug("Force mode disabled")
        db_file = configuration.get('GLOBAL', 'database')
        assert(db_file != None)
        if (os.path.isfile(db_file)) :
            raise Exceptions.ForceNeeded("database file "
                                         "`" + db_file + "' "
                                         "already exists")

    # Work

    # We are in force mode (which means we must write the DB whatsover) or the
    # DB file is not present at all ...

    db = DB.Database()
    tree = None
    db.save(db_file, tree)

    debug("DB file created")

    return 0

# Test
if (__name__ == '__main__') :
    debug("Test completed")
    sys.exit(0)
