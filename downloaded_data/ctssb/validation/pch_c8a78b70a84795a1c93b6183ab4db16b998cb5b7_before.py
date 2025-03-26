import argparse
import os

from .utils import cmd_output, RexList


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('directories', nargs='*', help="")
    parser.add_argument('--ignore', action='append', help="")

    args = parser.parse_args(argv)
    dirs = args.directories
    ignored = RexList()
    if args.ignore:
        ignored = RexList(args.ignore)

    if not dirs:
        dirs = [os.curdir]

    dirs = list(map(os.path.realpath, dirs))

    output = cmd_output("git", "ls-files", "--others", "--exclude-standard", *dirs)
    if output:
        results = output.split("\n")
        filenames = results - ignored
        if filenames:
            print("\n".join(filenames))
            return 1
    return 2


if __name__ == '__main__':
    exit(main())
