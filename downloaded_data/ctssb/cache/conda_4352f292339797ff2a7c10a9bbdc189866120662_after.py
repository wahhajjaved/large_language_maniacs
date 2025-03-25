# (c) 2012-2013 Continuum Analytics, Inc. / http://continuum.io
# All Rights Reserved
#
# conda is distributed under the terms of the BSD 3-clause license.
# Consult LICENSE.txt or http://opensource.org/licenses/BSD-3-Clause.

from argparse import RawDescriptionHelpFormatter

import common


help = "Remove a list of packages from a specified conda environment."
descr = help + """
Normally, only the specified package is removed, and not the packages
which may depend on the package.  Hence this command should be used
with caution.
"""
example = """
examples:
    conda remove -n myenv scipy

"""

def configure_parser(sub_parsers):
    p = sub_parsers.add_parser(
        'remove',
        formatter_class = RawDescriptionHelpFormatter,
        description = descr,
        help = help,
        epilog = example,
    )
    common.add_parser_yes(p)
    p.add_argument(
        "--all",
        action = "store_true",
        help = "remove all packages, i.e. the entire environment",
    )
    p.add_argument(
        "--features",
        action = "store_true",
        help = "remove features (instead of packages)",
    )
    common.add_parser_prefix(p)
    common.add_parser_quiet(p)
    p.add_argument(
        'package_names',
        metavar = 'package_name',
        action = "store",
        nargs = '*',
        help = "package names to remove from environment",
    )
    p.set_defaults(func=execute)


def execute(args, parser):
    import sys

    import conda.plan as plan


    if not (args.all or args.package_names):
        sys.exit('Error: no package names supplied,\n'
                 '       try "conda remove -h" for more details')

    prefix = common.get_prefix(args)

    index = None
    if args.features:
        from conda.api import get_index

        index = get_index()
        features = set(args.package_names)
        actions = plan.remove_features_actions(prefix, index, features)

    elif args.all:
        from conda.install import linked

        if plan.is_root_prefix(prefix):
            sys.exit('Error: cannot remove root environment,\n'
                     '       add -n NAME or -p PREFIX option')

        actions = {plan.PREFIX: prefix,
                   plan.UNLINK: sorted(linked(prefix))}

    else:
        specs = common.specs_from_args(args.package_names)
        no_rm = 'python', 'pycosat', 'conda'
        if (plan.is_root_prefix(prefix) and
            common.names_in_specs(no_rm, specs)):
            sys.exit('Error: cannot remove %s from root environment' %
                     ', '.join(no_rm))
        actions = plan.remove_actions(prefix, specs)

    if plan.nothing_to_do(actions):
        print 'No packages found to remove from environment: %s' % prefix
        return

    print
    print "Package plan for package removal in environment %s:" % prefix
    plan.display_actions(actions)

    common.confirm(args)
    plan.execute_actions(actions, index, verbose=not args.quiet)
