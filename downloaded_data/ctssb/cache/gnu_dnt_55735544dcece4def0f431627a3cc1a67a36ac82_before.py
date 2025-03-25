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
from   ID         import *

def description() :
    return "manage current configuration"

def _key_exists(configuration, section, option) :
    debug("configuration = "
          "`" + str(configuration) + "', "
          "section = "
          "`" + section + "', "
          "option = "
          "`" + option + "'")

    if (section == None or section == "") :
        return False
    if (not configuration.has_section(section)) :
        return False
    if (option == None or option == "") :
        return False
    if (not configuration.has_option(section, option)) :
        return False
    return True

def do(configuration, arguments) :
    command = Command("config")

    # Parameters setup
    command.add_option("-s", "--set",
		       action = "store_true",
		       dest   = "set",
		       help   = "set a (local) configuration key value")
    command.add_option("-g", "--get",
		       action = "store_true",
		       dest   = "get",
		       help   = "get a configuration key value")
    command.add_option("-S", "--show",
		       action = "store_true",
		       dest   = "show",
		       help   = "show all configuration values")

    command.add_option("-k", "--key",
		       action = "store",
		       dest   = "key",
		       help   = "specify key to get/set")
    command.add_option("-v", "--value",
		       action = "store",
		       dest   = "value",
		       help   = "specify value to set")

    # Parameters parsing
    (opts, args) = command.parse_args(arguments)

    # Parameters checks
    if (opts.set != True and opts.get != True and opts.show != True) :
	raise Exceptions.MissingParameters()
    if (opts.set == True and opts.get == True) :
	raise Exceptions.TooManyParameters()
    if ((opts.set == True or opts.get == True) and opts.show == True) :
	raise Exceptions.WrongParameters("set or get with show cannot be mixed")

    if (opts.set == True) :
	if (opts.key == None) :
	    raise Exceptions.MissingParameters("key in order to set a "
					       "configuration entry")
	if (opts.value == None) :
	    raise Exceptions.MissingParameters("value in order to set a "
					       "configuration entry")
    if (opts.get == True) :
	if (opts.key == None) :
	    raise Exceptions.MissingParameters("key in order to get a "
					       "configuration entry")
    # Work
    try :
	if (opts.get == True) :
	    debug("Performing get")
	    assert(opts.key != None)

	    try :
		(section, option) = opts.key.rsplit('.',1)
	    except ValueError :
		raise Exceptions.WrongParameters("key "
                                                 "`" + opts.key + "' "
                                                 "is malformed")
	    debug("section = `" + section + "'")
	    debug("option  = `" + option + "'")

            if (not _key_exists(configuration, section, option)) :
                    raise Exceptions.WrongParameters("key "
                                                     "`" + opts.key + "' "
                                                     "is unavailable")

	    debug("Getting value for `" + section + "." + option + "'")
	    value = configuration.get(section, option, raw = True)
	    sys.stdout.write(str(value) + '\n')

	elif (opts.set == True) :
	    debug("Performing set")
	    assert(opts.key   != None)
	    assert(opts.value != None)

	    try :
		(section, option) = opts.key.rsplit('.',1)
	    except ValueError :
		raise Exceptions.WrongParameters("key "
                                                 "`" + opts.key + "' "
                                                 "is malformed")
	    debug("section = `" + section + "'")
	    debug("option  = `" + option     + "'")

	    value = opts.value
	    debug("value   = `" + value   + "'")

	    debug("Setting `" + section + "." + option + "' to `" + value + "'")
	    configuration.set(section, option, value)

	elif (opts.show == True) :
	    debug("Showing all key/value pairs")
	    # Compute maximum key length
	    l = 0
	    for s in configuration.sections() :
		for o in configuration.options(s) :
		    l = max(l, len(s + "." + o))

	    # Write all key-value pairs
	    for s in configuration.sections() :
		for o in configuration.options(s) :
		    v = configuration.get(s, o, raw = True)
		    print(("%-" + str(l) + "s = %s")
			  %(s + "." + o,  str(v)))

	else :
	    bug()

#    except Configuration.NoOptionError, e :
#	error(e)
#	return 1
    except Exceptions.Parameters, e :
	error(e)
	return 1
    except :
	bug()

    debug("Success")

    return 0

# Test
if (__name__ == '__main__') :
    debug("Test completed")
    sys.exit(0)
