# (c) Continuum Analytics, Inc. / http://continuum.io
# All Rights Reserved
#
# conda is distributed under the terms of the BSD 3-clause license.
# Consult LICENSE.txt or http://opensource.org/licenses/BSD-3-Clause.

from __future__ import print_function, division, absolute_import

from conda.cli import common


descr = "Low-level conda package utility. (EXPERIMENTAL)"


def configure_parser(sub_parsers):
    p = sub_parsers.add_parser('package', description=descr, help=descr)

    common.add_parser_prefix(p)
    p.add_argument(
        '-w', "--which",
        action = "store_true",
        help = "given some PATH print which conda package the file came from",
    )
    p.add_argument(
        '-L', "--ls-files",
        metavar = 'PKG-NAME',
        action  = "store",
        help    = "list all files belonging to specified package",
    )
    p.add_argument(
        '-r', "--reset",
        action  = "store_true",
        help    = "remove all untracked files and exit",
    )
    p.add_argument(
        '-u', "--untracked",
        action  = "store_true",
        help    = "display all untracked files and exit",
    )
    p.add_argument(
        "--pkg-name",
        action  = "store",
        default = "unknown",
        help    = "package name of the created package",
    )
    p.add_argument(
        "--pkg-version",
        action  = "store",
        default = "0.0",
        help    = "package version of the created package",
    )
    p.add_argument(
        "--pkg-build",
        action  = "store",
        default = 0,
        help    = "package build number of the created package",
    )
    p.add_argument(
        'path',
        metavar = 'PATH',
        action = "store",
        nargs = '*',
    )
    p.set_defaults(func=execute)

def listPackageFiles(pkgName=None):
    import os
    import re
    import conda.config as config
    from conda.misc import walk_prefix

    pkgsDir = config.pkgs_dirs[0]
    allDirNames = []
    pattern = re.compile(pkgName, re.I)

    print('\nINFO: The location for available packages: %s' % (pkgsDir))

    for dir in os.listdir(pkgsDir):
        ignoreDirs = [ '_cache-0.0-x0', 'cache' ]

        if dir in ignoreDirs:
            continue

        if not os.path.isfile(pkgsDir+"/"+dir):
            match = pattern.match(dir)

            if match:
                allDirNames.append(dir)

    numOfAllDirNames = len(allDirNames)
    dirNumWidth = len(str(numOfAllDirNames))

    if numOfAllDirNames == 0:
        print("\n\tWARN: There is NO '%s' package.\n" % (pkgName))
        return 1
    elif numOfAllDirNames >= 2:
        print("\n\tWARN: Ambiguous package name ('%s'), choose one name from below list:\n" % (pkgName))

        num = 0
        for dir in allDirNames:
            num += 1
            print("\t[ {num:>{width}} / {total} ]: {dir}".format(num=num, width=dirNumWidth, total=numOfAllDirNames, dir=dir))
        print("")
        return 1

    fullPkgName = allDirNames[0]

    print("INFO: All files belonging to '%s' package:\n" % (fullPkgName))

    pkgDir = pkgsDir+"/"+fullPkgName

    ret = walk_prefix(pkgDir, ignorePredefinedFiles=True)
    for item in ret:
        print(pkgDir+"/"+item)

def execute(args, parser):
    import sys

    from conda.misc import untracked
    from conda.packup import make_tarbz2, remove


    prefix = common.get_prefix(args)

    if args.which:
        from conda.misc import which_package

        for path in args.path:
            for dist in which_package(path):
                print('%-50s  %s' % (path, dist))
        return

    if args.ls_files:
        if listPackageFiles(args.ls_files) == 1:
            sys.exit(1)
        else:
            return

    if args.path:
        sys.exit("Error: no positional arguments expected.")

    print('# prefix:', prefix)

    if args.reset:
        remove(prefix, untracked(prefix))
        return

    if args.untracked:
        files = sorted(untracked(prefix))
        print('# untracked files: %d' % len(files))
        for fn in files:
            print(fn)
        return

    make_tarbz2(prefix,
                name = args.pkg_name.lower(),
                version = args.pkg_version,
                build_number = int(args.pkg_build))
