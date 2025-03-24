#!/usr/bin/env python
import sys
from optparse import OptionParser
from zsplitjoin import split_file


def main():
    usage = 'Usage: zsplit.py [options] [file]\n outputs will have extensions .part[n...]'
    opar = OptionParser(usage=usage)
    opar.add_option("-n", "--number", dest="number",
                    help="number of files", type="int", default=None)
    opar.add_option("-s", "--size", dest="size",
                    help="splitted file size", type="str", default=None)
    opar.add_option("-o", "--output", dest="output",
                    help="output file name", type="str", default=None)
    opar.add_option("-c", "--chunk", dest="chunk",
                    help="chunk size", type="str", default='1K')

    options, args = opar.parse_args(sys.argv)
    if len(args) <= 1:
        print('invalid input')
        sys.exit(0)

    split_file(
        args[1],
        number_of_files=options.number,
        new_file_size=options.size,
        output_file_name=options.output,
        chunk_size=options.chunk
    )


if __name__ == '__main__':
    main()
