#!/usr/bin/env python

__version__ = "20130623.0800"

import os
import sys
import time
import re
import subprocess
import datetime
import random
import zlib
import distutils.spawn

from optparse import OptionParser

parent = os.path.dirname
basename = os.path.basename
join = os.path.join


BAD_FNAME_RE = re.compile(r"""[\x00"'\\]+""")

def check_filename(fname):
	"""
	Raise L{ValueError} on any filename that can't be safely passed into a quoted
	shell command.
	"""
	if re.findall(BAD_FNAME_RE, fname):
		raise ValueError("Bad filename %r" % (fname,))


def filename_without_prefix(fname, prefix):
	if not fname.startswith(prefix + "/"):
		raise ValueError("%r does not start with %" % (fname, prefix + "/"))
	return fname.replace(prefix + "/", "", 1)


def try_makedirs(p):
	try:
		os.makedirs(p)
	except OSError:
		pass


def gunzip_string(s):
	return zlib.decompress(s, 16 + zlib.MAX_WBITS)


class BadWARC(Exception):
	pass



def get_info_from_warc_fname(fname):
	"""
	Where fname is absolute path, or at least includes the uploader parent dir
	"""
	uploader = basename(parent(fname))
	_, item_name, _, _ = basename(fname).split('-')
	return dict(uploader=uploader, item_name=item_name, basename=basename(fname))


def check_warc(fname, info, bzip2_bundle, exes):
	check_filename(fname)

	args = [exes['sh'], '-c', r"""
trap '' INT tstp 30;
%(gunzip)s --to-stdout '%(fname)s'""".replace("\n", "") % dict(
		fname=fname, **exes)]
	gunzip_proc = subprocess.Popen(args, stdout=subprocess.PIPE, bufsize=4*1024*1024, close_fds=True)
	# TODO: do we need to read stderr continuously as well to avoid deadlock?
	try:
		while True:
			block = gunzip_proc.stdout.read(4*1024*1024)
			if bzip2_bundle:
				bzip2_bundle.write(block)
			if not block:
				break
	finally:
		_, stderr = gunzip_proc.communicate()
		if stderr:
			print stderr
			raise BadWARC("Got stderr from gunzip process: %r" % (stderr,))
		if gunzip_proc.returncode != 0:
			raise BadWARC("Got process exit code %r from gunzip process" % (gunzip_proc.returncode,))


def get_mtime(fname):
	try:
		s = os.stat(fname)
	except OSError:
		return None
	return s.st_mtime


def check_input_base(options, verified_dir, bad_dir, bzip2_bundle, exes, full_date):
	stopfile = join(os.getcwd(), "STOP")
	print "WARNING: To stop, do *not* use ctrl-c; instead, touch %s" % (stopfile,)
	initial_stop_mtime = get_mtime(stopfile)

	start = time.time()
	size_total = 0
	count = 0
	for directory, dirnames, filenames in os.walk(options.input_base):
		if basename(directory).startswith("."):
			print "Skipping dotdir %r" % (directory,)
			continue

		for f in filenames:
			if get_mtime(stopfile) != initial_stop_mtime:
				print "Stopping because %s was touched" % (stopfile,)
				return

			if f.startswith("."):
				print "Skipping dotfile %r" % (f,)
				continue

			fname = os.path.join(directory, f)
			if fname.endswith('.warc.gz'):
				count += 1
				if options.check_limit and count > options.check_limit:
					print "Stopping because --check-limit=%r was reached" % (options.check_limit,)
					return

				size_total += os.stat(fname).st_size
				def get_mb_sec():
					return ("%.2f MB/s" % (size_total/(time.time() - start) / (1024 * 1024))).rjust(10)

				info = get_info_from_warc_fname(fname)
				try:
					check_warc(fname, info, bzip2_bundle, exes)
				except BadWARC:
					msg = "bad"
					dest_dir = bad_dir
				else:
					msg = "ok "
					dest_dir = verified_dir

				print get_mb_sec(), msg, filename_without_prefix(fname, options.input_base)

				if dest_dir:
					dest_fname = join(dest_dir, filename_without_prefix(fname, options.input_base))
					try_makedirs(parent(dest_fname))
					os.rename(fname, dest_fname)


def get_exes():
	bzip2_exe = distutils.spawn.find_executable('lbzip2')
	if not bzip2_exe:
		print "WARNING: Install lbzip2; this program is ~1.4x slower with vanilla bzip2"
		bzip2_exe = distutils.spawn.find_executable('bzip2')
		if not bzip2_exe:
			raise RuntimeError("lbzip2 or bzip2 not found in PATH")

	gunzip_exe = distutils.spawn.find_executable('gunzip')
	if not gunzip_exe:
		raise RuntimeError("gunzip not found in PATH")

	grep_exe = distutils.spawn.find_executable('grep')
	if not grep_exe:
		raise RuntimeError("grep not found in PATH")

	sh_exe = distutils.spawn.find_executable('sh')
	if not sh_exe:
		raise RuntimeError("sh not found in PATH")

	return dict(bzip2=bzip2_exe, gunzip=gunzip_exe, grep=grep_exe, sh=sh_exe)


def main():
	parser = OptionParser(usage="%prog [options]")

	parser.add_option("-i", "--input-base", dest="input_base", help="Base directory containing ./username/xxx.warc.gz files.")
	parser.add_option("-o", "--output-base", dest="output_base", help="Base directory to which to move input files; it will contain ./verified/username/xxx.warc.gz or ./bad/username/xxx.warc.gz.  Should be on the same filesystem as --input-base.")
	parser.add_option("-b", "--bzip2-bundle-dir", dest="bzip2_bundle_dir", help="Base directory to write warc.gz->.bz2 conversions to")
	parser.add_option("-c", "--check-limit", dest="check_limit", type="int", default=None, help="Exit after checking this many items")

	options, args = parser.parse_args()
	if not options.input_base:
		print "--input-base is required"
		print
		parser.print_help()
		sys.exit(1)

	if not options.output_base:
		print "--output-base not specified; files in --input-base will not be moved"

	if not options.bzip2_bundle_dir:
		print "--bzip2-bundle-dir not specified; bz2 bundles will not be written"

	if options.output_base:
		verified_dir = join(options.output_base, "verified")
		try_makedirs(verified_dir)
		bad_dir = join(options.output_base, "bad")
		try_makedirs(bad_dir)
	else:
		verified_dir = None
		bad_dir = None

	exes = get_exes()

	now = datetime.datetime.now()
	full_date = now.isoformat().replace("T", "_").replace(':', '-') + "_" + str(random.random())[2:8]

	if options.bzip2_bundle_dir:
		# trap '' INT tstp 30; prevents sh from catching SIGINT (ctrl-c).  If untrapped,
		# bzip2 or lbzip2 will be killed when you hit ctrl-c, leaving you with a corrupt .bz2.
		# (Sadly, this `trap` does not seem to work with lbzip2.)
		#
		# We use close_fds=True because otherwise .communicate() later deadlocks on
		# Python 2.6.  See http://stackoverflow.com/questions/14615462/why-does-communicate-deadlock-when-used-with-multiple-popen-subprocesses
		bzip2_bundle_fname = join(options.lists_dir, full_date + ".bz2")
		check_filename(bzip2_bundle_fname)
		assert not os.path.exists(bzip2_bundle_fname), bzip2_bundle_fname
		try_makedirs(parent(bzip2_bundle_fname))
		bzip2_bundle_proc = subprocess.Popen(
			[exes['sh'], '-c', r"trap '' INT tstp 30; %(bzip2)s > %(bzip2_bundle_fname)s" %
				dict(bzip2_bundle_fname=bzip2_bundle_fname, **exes)],
			stdin=subprocess.PIPE, bufsize=4*1024*1024, close_fds=True)
		bzip2_bundle = bzip2_bundle_fname.stdin
	else:
		bzip2_bundle = None

	try:
		check_input_base(options, verified_dir, bad_dir, bzip2_bundle, exes, full_date)
	finally:
		if bzip2_bundle is not None:
			bzip2_bundle.close()
			_, stderr = bzip2_bundle_proc.communicate()
			if stderr:
				print stderr


if __name__ == '__main__':
	main()
