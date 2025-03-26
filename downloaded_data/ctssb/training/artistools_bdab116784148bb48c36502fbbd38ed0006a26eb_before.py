#!/usr/bin/env python3

import math
import numpy as np
import os.path
import pandas as pd
from astropy import constants as const
from pathlib import Path

import artistools as at
import artistools.deposition
import artistools.lightcurve
import artistools.macroatom
import artistools.makemodel.botyanski2017
import artistools.nltepops
import artistools.nonthermal
import artistools.radfield
import artistools.spectra
import artistools.transitions

modelpath = Path('tests', 'data')
outputpath = Path('tests', 'output')
specfilename = modelpath / 'spec.out'
emissionfilename = modelpath / 'emissiontrue.out.gz'
absorptionfilename = modelpath / 'absorption.out.gz'


def test_timestep_times():
    timearray = at.get_timestep_times(modelpath)
    assert len(timearray) == 100
    assert timearray[0] == '250.421'
    assert timearray[-1] == '349.412'


def check_spectrum(dfspectrum):
    assert math.isclose(max(dfspectrum['f_lambda']), 2.548532804918824e-13, abs_tol=1e-5)
    assert min(dfspectrum['f_lambda']) < 1e-9
    assert math.isclose(np.mean(dfspectrum['f_lambda']), 1.0314682640070206e-14, abs_tol=1e-5)


def test_get_spectrum():
    dfspectrum = at.spectra.get_spectrum(specfilename, 55, 65, fnufilterfunc=None)
    assert len(dfspectrum['lambda_angstroms']) == 1000
    assert len(dfspectrum['f_lambda']) == 1000
    assert abs(dfspectrum['lambda_angstroms'].values[-1] - 29920.601421214415) < 1e-5
    assert abs(dfspectrum['lambda_angstroms'].values[0] - 600.75759482509852) < 1e-5
    check_spectrum(dfspectrum)
    lambda_min = dfspectrum['lambda_angstroms'].values[0]
    lambda_max = dfspectrum['lambda_angstroms'].values[-1]
    dfspectrumpkts = at.spectra.get_spectrum_from_packets(
        [os.path.join(modelpath, 'packets00_0000.out.gz')], 55, 65, lambda_min=lambda_min, lambda_max=lambda_max)
    check_spectrum(dfspectrumpkts)


def test_get_flux_contributions():
    timestepmin = 40
    timestepmax = 80
    dfspectrum = at.spectra.get_spectrum(
        specfilename, timestepmin=timestepmin, timestepmax=timestepmax, fnufilterfunc=None)

    integrated_flux_specout = -np.trapz(dfspectrum['f_lambda'], x=dfspectrum['lambda_angstroms'])

    specdata = pd.read_csv(specfilename, delim_whitespace=True)
    timearray = specdata.columns.values[1:]
    arraynu = specdata.loc[:, '0'].values
    arraylambda_angstroms = const.c.to('angstrom/s').value / arraynu

    contribution_list, array_flambda_emission_total = at.spectra.get_flux_contributions(
        emissionfilename, absorptionfilename, timearray, arraynu,
        xmin=-1, xmax=np.inf, timestepmin=timestepmin, timestepmax=timestepmax)

    integrated_flux_emission = -np.trapz(array_flambda_emission_total, x=arraylambda_angstroms)

    # total spectrum should be equal to the sum of all emission processes
    print(f'Integrated flux from spec.out:     {integrated_flux_specout}')
    print(f'Integrated flux from emission sum: {integrated_flux_emission}')
    assert math.isclose(integrated_flux_specout, integrated_flux_emission, rel_tol=4e-3)

    # check each bin is not out by a large fraction
    diff = [abs(x - y) for x, y in zip(array_flambda_emission_total, dfspectrum['f_lambda'].values)]
    print(f'Max f_lambda difference {max(diff) / integrated_flux_specout.value}')
    assert max(diff) / integrated_flux_specout.value < 2e-3


def test_spectraplot():
    at.spectra.main(modelpath=modelpath, outputfile=outputpath, timemin=290, timemax=320)
    at.spectra.main(modelpath=modelpath, outputfile=os.path.join(outputpath, 'spectrum_from_packets.pdf'),
                    timemin=290, timemax=320, frompackets=True)
    at.spectra.main(modelpath=modelpath, output_spectra=True)
    at.spectra.main(modelpath=modelpath, outputfile=outputpath, timemin=290, timemax=320, emissionabsorption=True)
    at.spectra.main(modelpath=modelpath, outputfile=outputpath, timemin=290, timemax=320, emissionabsorption=True,
                    nostack=True)


def test_plotters():
    at.nltepops.main(modelpath=modelpath, outputfile=outputpath, timedays=300)
    at.lightcurve.main(modelpath=modelpath, outputfile=outputpath)
    at.lightcurve.main(modelpath=modelpath, frompackets=True,
                       outputfile=os.path.join(outputpath, 'lightcurve_from_packets.pdf'))
    at.nonthermal.main(modelpath=modelpath, outputfile=outputpath, timedays=300)
    at.transitions.main(modelpath=modelpath, outputfile=outputpath, timedays=300)
    at.estimators.main(modelpath=modelpath, outputfile=outputpath, timedays=300)
    at.macroatom.main(modelpath=modelpath, outputfile=outputpath, timestep=10)
    assert at.radfield.main(modelpath=modelpath, outputfile=outputpath) == 0


def test_makemodel():
    at.makemodel.botyanski2017.main(outputpath=outputpath)


def test_deposition():
    at.deposition.main(modelpath=modelpath)


def test_menu():
    at.main()
    at.showtimesteptimes(modelpath=modelpath)
    at.showtimesteptimes(specfilename=(modelpath / 'spec.out'))


def test_spencerfano():
    at.spencerfano.main(modelpath=modelpath, timedays=300, makeplot=True, npts=200, outputfile=outputpath)


def test_magnitudes_plot():
    at.lightcurve.main(modelpath=modelpath, magnitude=True, outputfile=outputpath)
