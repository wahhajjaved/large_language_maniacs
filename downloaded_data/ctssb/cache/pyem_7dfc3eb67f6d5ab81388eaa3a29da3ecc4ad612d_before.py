#!/usr/bin/env python2.7
# Copyright (C) 2017 Daniel Asarnow
# University of California, San Francisco
#
# Generate subparticles for "local reconstruction" methods.
# See help text and README file for more information.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
from __future__ import print_function
import glob
import logging
import numpy as np
import os
import os.path
import sys
import xml.etree.cElementTree as etree
from pyem import geom
from pyem import star
from pyem import util


def main(args):
    log = logging.getLogger(__name__)
    log.setLevel(logging.INFO)
    hdlr = logging.StreamHandler(sys.stdout)
    if args.quiet:
        hdlr.setLevel(logging.WARNING)
    else:
        hdlr.setLevel(logging.INFO)
    log.addHandler(hdlr)

    if args.target is None and args.sym is None:
        log.error("At least a target or symmetry group must be provided via --target or --sym")
        return 1
    elif args.target is not None and args.boxsize is None and args.origin is None:
        log.error("An origin must be provided via --boxsize or --origin")
        return 1

    if args.target is not None:
        try:
            args.target = np.array([np.double(tok) for tok in args.target.split(",")])
        except:
            log.error("Target must be comma-separated list of x,y,z coordinates")
            return 1

    if args.origin is not None:
        if args.boxsize is not None:
            log.warn("--origin supersedes --boxsize")
        try:
            args.origin = np.array([np.double(tok) for tok in args.origin.split(",")])
        except:
            log.error("Origin must be comma-separated list of x,y,z coordinates")
            return 1
    
    if args.sym is not None:
        args.sym = util.relion_symmetry_group(args.sym)

    df = star.parse_star(args.input)

    if args.apix is None:
        args.apix = star.calculate_apix(df)
        if args.apix is None:
            log.warn("Could not compute pixel size, default is 1.0 Angstroms per pixel")
            args.apix = 1.0
            df[star.Relion.MAGNIFICATION] = 10000
            df[star.DETECTORPIXELSIZE] = 1.0

    if args.cls is not None:
        df = star.select_classes(df, args.cls)

    if args.target is not None:
        if args.origin is not None:
            args.origin /= args.apix
        elif args.boxsize is not None:
            args.origin = np.ones(3) * args.boxsize / 2
        args.target /= args.apix
        c = args.target - args.origin
        c = np.where(np.abs(c) < 1, 0, c)  # Ignore very small coordinates.
        d = np.linalg.norm(c)
        ax = c / d
        cm = util.euler2rot(*np.array([np.arctan2(ax[1], ax[0]), np.arccos(ax[2]), np.deg2rad(args.psi)]))
        ops = [op.dot(cm) for op in args.sym] if args.sym is not None else [cm]
        dfs = [star.transform_star(df, op.T, -d, rotate=args.shift_only, invert=args.target_invert, adjust_defocus=args.adjust_defocus) for op in ops]
    elif args.sym is not None:
        dfs = list(subparticle_expansion(df, args.sym, -args.displacement / args.apix))
    else:
        log.error("At least a target or symmetry group must be provided via --target or --sym")
        return 1
 
    if args.recenter:
        for s in dfs:
            star.recenter(s, inplace=True)
    
    if args.suffix is None and not args.skip_join:
        if len(dfs) > 1:
            df = util.interleave(dfs)
        else:
            df = dfs[0]
        star.write_star(args.output, df)
    else:
        for i, s in enumerate(dfs):
            star.write_star(os.path.join(args.output, args.suffix + "_%d" % i), s)
    return 0


def subparticle_expansion(s, ops=None, dists=None, rots=None):
    if ops is None:
        ops = [np.eye(3)]
    if rots is None:
        # rots = [util.euler2rot(*np.deg2rad(r[1])) for r in s[star.Relion.ANGLES].iterrows()]
        rots = geom.e2r_vec(np.deg2rad(s[star.Relion.ANGLES].values))
    if dists is not None:
        if np.isscalar(dists):
            dists = [dists] * len(ops)
        for i in range(len(ops)):
            yield star.transform_star(s, ops[i], dists[i], rots=rots)
    else:
        for op in ops:
            yield star.transform_star(s, op, rots=rots)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="STAR file with source particles")
    parser.add_argument("output", help="Output file path (and prefix for output files)")
    parser.add_argument("--apix", "--angpix", help="Angstroms per pixel (calculate from STAR by default)", type=float)
    parser.add_argument("--boxsize", help="Particle box size in pixels (used to define origin only)", type=int)
    parser.add_argument("--class", help="Keep this class in output, may be passed multiple times",
                        action="append", type=int, dest="cls")
    parser.add_argument("--displacement", help="Distance of new origin from symmetrix axis in Angstroms",
                        type=float, default=0)
    parser.add_argument("--origin", help="Origin coordinates in Angstroms", metavar="x,y,z")
    parser.add_argument("--target", help="Target coordinates in Angstroms", metavar="x,y,z")
    parser.add_argument("--target-invert", help="Undo target pose transformation", action="store_true")
    parser.add_argument("--psi", help="Additional in-plane rotation of target in degrees", type=float, default=0)
    parser.add_argument("--recenter", help="Recenter subparticle coordinates by subtracting X and Y shifts (e.g. for "
                                           "extracting outside Relion)", action="store_true")
    parser.add_argument("--adjust-defocus", help="Add Z component of shifts to defocus", action="store_true")
    parser.add_argument("--shift-only", help="Keep original view axis after target transformation", action="store_false")
    parser.add_argument("--quiet", help="Don't print info messages", action="store_true")
    parser.add_argument("--skip-join", help="Force multiple output files even if no suffix provided",
                        action="store_true", default=False)
    parser.add_argument("--suffix", help="Suffix for multiple output files")
    parser.add_argument("--sym", help="Symmetry group for whole-particle expansion or symmetry-derived subparticles ("
                                      "Relion conventions)")

    sys.exit(main(parser.parse_args()))

