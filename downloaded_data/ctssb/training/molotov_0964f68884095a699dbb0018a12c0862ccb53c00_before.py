import os
import sys
import argparse
from importlib import import_module
from importlib.util import spec_from_file_location, module_from_spec

from molotov.fmwk import runner, get_scenarios
from molotov import __version__


def main():
    parser = argparse.ArgumentParser(description='Load test.')

    parser.add_argument('scenario', default="loadtest",
                        help="path or module name that contains scenarii")

    parser.add_argument('--statsd', action='store_true', default=False,
                        help='Sends metrics to Statsd.')

    parser.add_argument('--statsd-host', default='localhost',
                        help='Statsd host.')

    parser.add_argument('--statsd-port', default=8125, type=int,
                        help='Statsd port.')

    parser.add_argument('--version', action='store_true', default=False,
                        help='Displays version and exits.')

    parser.add_argument('-p', '--processes', action='store_true',
                        default=False,
                        help='Uses processes instead of threads.')

    parser.add_argument('-v', '--verbose', action='store_true', default=False,
                        help='Verbose')

    parser.add_argument('-u', '--users', help='Number of users',
                        type=int, default=1)

    parser.add_argument('-d', '--duration', help='Duration in seconds',
                        type=int, default=10)

    parser.add_argument('-q', '--quiet', action='store_true', default=False,
                        help='Quiet')

    parser.add_argument('-x', '--exception', action='store_true',
                        default=False,
                        help='Stop on first failure.')

    args = parser.parse_args()

    if args.version:
        print(__version__)
        sys.exit(0)

    return run(args)


def run(args):
    if os.path.exists(args.scenario):
        spec = spec_from_file_location("loadtest", args.scenario)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        try:
            import_module(args.scenario)
        except ImportError:
            print('Cannot import %r' % args.scenario)
            sys.exit(1)

    if len(get_scenarios()) == 0:
        print('You need at least one scenario. No scenario was found.')
        sys.exit(1)

    if args.verbose and args.quiet:
        print("You can't use -q and -v at the same time")
        sys.exit(1)

    res = runner(args)
    tok, tfailed = 0, 0

    for ok, failed in res:
        tok += ok
        tfailed += failed

    print('')
    print('%d OK, %d Failed' % (tok, tfailed))


if __name__ == '__main__':
    main()
