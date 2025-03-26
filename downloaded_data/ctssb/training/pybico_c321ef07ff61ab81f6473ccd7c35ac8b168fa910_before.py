import getopt
import sys
import string

from loader import Loader
from saver import Saver
from dbwrapper import DBWrapper as DB

PYBICO_VERBOSE = False

def usage():
	print("usage: pybico [options]")
	print("\toptions:")
	print("\t -h, --help\t print out help")
	print("\t -v\t verbose mode")
	print("\t -l\t import file path to load")
	print("\t -s\t export file path to save")
	print("\t -i\t import format (txt, id)")
	print("\t -e\t export format (xlsx)")
	print("\t -u\t database user")
	print("\t -p\t path to database password")

def main(argv):
	global PYBICO_VERBOSE

	try:
		opts, args = getopt.getopt(argv, "hvl:s:i:e:u:p:", ["help"])
	except getopt.GetoptError as err:
		print(str(err))
		usage()
		sys.exit(2)

	PYBICO_VERBOSE = False
	load_format = "txt"
	save_format = "xlsx"
	load_filename = ""
	save_filename = ""
	password_path = ""
	user = ""

	for o, a in opts:
		if o == "-v":
			PYBICO_VERBOSE = True
		elif o in ("-h", "--help"):
			usage()
			sys.exit()
		elif o == "-u":
			user = a
		elif o == "-p":
			password_path = a
		elif o == "-l":
			load_filename = a
		elif o == "-s":
			save_filename = a
		elif o == "-i":
			load_format = a
		elif o == "-e":
			save_format = a
		else:
			assert False, "unhandled option"

	f = open(password_path, 'r')
	password = f.read()

	db = DB(user, password)
	if load_filename != "":
		l = Loader()
		data = l.load(load_format, load_filename)
		db.add(data)
	if save_filename != "":
		data = db.get()
		s = Saver()
		s.save(data, save_format, save_filename)

if __name__ == '__main__':
	main(sys.argv[1:])
