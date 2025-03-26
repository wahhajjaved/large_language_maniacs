#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
from argparse_tools import parse_range
import h5py
from lmfit import Model
import logging
import scipy
from scipy import arange, average, cos, float32, pi, polyfit, polyval, sqrt, std
import sys


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", help="Name of the HDF5 file")
    parser.add_argument("-f", "--force",
                        help="Overwrite previous reconstructions", action="store_true")
    parser.add_argument("-e", "--eta", help="Detection efficiency eta", type=float, default=.8)
    parser.add_argument("-s", "--scans", help="Select scans to treat", type=parse_range, default="all")
    return parser.parse_args()


def create_dataset(args, h5, name, shape):
    if name in h5.keys():
        if args.force:
            print ("Old {} found. Force active, overwriting old data.".format(name))
            return h5[name]
        else:
            print ("Old {} found. "
                   "If you want to overwrite them, use --force. Aborting.".format(name))
            sys.exit(1)
    return h5.create_dataset(name, shape, compression="gzip", dtype="float32")


def setup_datasets(args, h5):
    shape = h5["raw_quadratures"].shape
    no_scans, no_steps, no_angles, no_pulses = shape
    ds_q = create_dataset(args, h5, "standardized_quadratures", shape)
    ds_a = create_dataset(args, h5, "angles", (no_scans, no_angles))
    ds_phi_0 = create_dataset(args, h5, "phi_0", (no_scans, no_steps))
    return ds_phi_0, ds_a, ds_q


def cosmod(x, V0, A, omega, phi0):
    return V0 + A*cos(omega*x + phi0)


def center_on_cos(raw_quadratures, omega=None):
    mean = scipy.average(raw_quadratures, axis=1)
    no_angles, no_pulses = raw_quadratures.shape
    model = Model(cosmod)
    model.set_param_hint("V0", value=scipy.average(mean))
    model.set_param_hint("A", value=(mean.max()-mean.min())/2.)
    model.set_param_hint("phi0", value=0.)
    if omega==None:
        # determine omega (usually from first step)
        model.set_param_hint("omega", value=2.*pi/(no_angles*.7))
    else:
        # omega is already fixed
        model.set_param_hint("omega", value=omega, vary=False)
    model.make_params()
    steps = scipy.arange(no_angles)
    res = model.fit(mean, x=steps)
    omega_param = res.params["omega"]
    if omega==None:
        appx_omega = float(omega_param)
        N = int(round(pi/appx_omega))
        omega = pi/N
        omega_param.set(omega, vary=False)
        res.fit(mean, x=steps)
    mean_fit = res.eval(x=steps)
    offset = mean-mean_fit
    aligned_quadratures = raw_quadratures - scipy.tile(offset, (no_pulses, 1)).T
    centered_quadratures = aligned_quadratures - float(res.params["V0"])
    return centered_quadratures, float(omega_param), float(res.params["phi0"])


def vacuum_correct(quadratures, vacuum_quadratures):
    gamma_prime = sqrt(2.)*average(std(vacuum_quadratures, axis=1))
    return quadratures/gamma_prime


def correct_intrastep_drift(quadratures, A=1.):
    no_steps, no_pulses = quadratures.shape
    pulses = scipy.arange(no_pulses)
    for i in xrange(quadratures.shape[0]):
        quads = quadratures[i]
        mean = average(quads)
        model = polyfit(pulses, quads, 5)
        quadratures[i] = quads - polyval(model, pulses) + mean
    return quadratures


def standardize_quadratures(raw_quadratures, vacuum_quadratures, omega=None):
    corrected_quadratures = correct_intrastep_drift(raw_quadratures)
    centered_quadratures, omega, phi_0 = center_on_cos(corrected_quadratures, omega)
    vacuum_corrected_quadratures = vacuum_correct(centered_quadratures, vacuum_quadratures)
    return omega, phi_0, vacuum_corrected_quadratures


def standardize_all_quadratures(args, h5):
    ds_phi_0, ds_a, ds_q = setup_datasets(args, h5)
    vacuum_quadratures = h5["vacuum_quadratures"][:]
    raw_ds = h5["raw_quadratures"]
    no_scans, no_steps, no_angles, no_pulses = raw_ds.shape
    if args.scans=="all":
        scans = xrange(no_scans)
    else:
        scans = args.scans
        no_scans = len(scans)
    omegas = scipy.empty((no_steps,), dtype=float32)
    for scan_no, i_scan in enumerate(scans, 1):
        sys.stderr.write("Starting scan {}, {} of {}:\n".format(i_scan, scan_no, no_scans))
        raw_quadratures = raw_ds[i_scan, 0, :, :]
        omega, phi_0, quadratures = standardize_quadratures(raw_quadratures, vacuum_quadratures)
        omegas[0] = omega
        ds_phi_0[i_scan, 0] = phi_0
        ds_q[i_scan, 0, :, :] = quadratures
        sys.stderr.write("\r{0:3.2%}".format(0.))
        for i_step in xrange(1, no_steps):
            raw_quadratures = raw_ds[i_scan, i_step, :, :]
            omega, phi_0, quadratures = standardize_quadratures(raw_quadratures, vacuum_quadratures, omega)
            omegas[i_step] = omega
            ds_phi_0[i_scan, i_step] = phi_0
            ds_q[i_scan, i_step, :, :] = quadratures
            sys.stderr.write("\r{0:3.2%}".format(float(i_step)/no_steps))
        sys.stderr.write("\r100.00%\n")
        angles = (arange(no_angles)*omega).astype(float32)
        ds_a[i_scan] = angles


def main():
    args = parse_args()
    h5 = h5py.File(args.filename, "r+")
    standardize_all_quadratures(args, h5)


if __name__ == "__main__":
    main()
