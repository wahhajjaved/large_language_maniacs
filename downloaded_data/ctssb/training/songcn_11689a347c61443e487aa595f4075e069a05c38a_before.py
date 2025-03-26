"""
The Slit class for SONG.

Aims:
-----
store parameters for reduction

"""

import os

import joblib
import numpy as np
from astropy import table
from astropy.io import fits

from twodspec import thar
from twodspec.aperture import Aperture
from twodspec.ccd import CCD
from . import __path__
import matplotlib.pyplot as plt
import warnings
from ipyparallel import Client
from collections import OrderedDict

SLITINFO_TENERIFE = """
Slit width(μm) width(") Length(") Resolution(λ/Δλ) Sampling(pix) 
1    ø20,ø100  -        -         -                -
2    ø20       ø0.69    -         180000           1.35
3    100       3.44     10        36000            6.76
4    60        2.06     10        60000            4.05
5    45        1.55     10        80000            3.03           √
6    36        1.24     10        100              2.43
7    30        1.03     10        120000           2.02
8    25        0.86     10        145000           1.69
9    2mm hole  -        -         -                -
"""

SLITINFO_DELINGHA = """
Slit width(μm) width(") Length(") Resolution(λ/Δλ) Sampling(pix)
1    ø20,ø100  -        -         -                -
2    ø20       ø0.69    -         180000           1.35
3    100       3.44     10        36000            6.76
4    60        2.06     10        60000            4.05
5    45        1.55     10        80000            3.03          *
6    36        1.24     10        100000           2.43          *
7    30        1.03     10        120000           2.02          *
8    25        0.86     10        145000           1.69          *
9    20        0.69     10        181000           1.35
10   2mm hole  -        -         -                -
"""


class Slit:
    # io directory
    extdir = None  # None or a directory

    node = ""
    # slit number
    slit = 5

    # master frames
    # I don't think in this algorithm the bias and flat should be written to fits.
    # They can just stay in the Slit instance.
    fps_bias = []
    fps_flat = []
    bias = 0
    flat = 0
    bg = 0

    # blaze & sensitivity
    blaze = 0
    sensitivity = 0

    # apertures
    ap = None

    # wavelength solutions
    tws = None

    # reduction parameters for SONG-China
    # 1. read images
    kwargs_read = dict(hdu=0, gain=1., ron=0., unit='adu', trim=None, rot90=0)
    # 2. trace orders
    kwargs_trace = dict(ap_width=15, sigma=7, maxdev=7, polydeg=4)
    # 3. scattered-light background for FLAT and STAR
    kwargs_background_flat = dict(q=(30, 1), kernel_size=(17, 17), sigma=(11, 7))
    kwargs_background_star = dict(q=(45, 45), kernel_size=(17, 17), sigma=(11, 7))
    # 4. normalize FLAT
    kwargs_normflat = dict(max_dqe=0.04, min_snr=20, smooth_blaze=5,
                           n_chunks=8, profile_oversample=10,
                           profile_smoothness=1e-2, num_sigma_clipping=20,
                           gain=1., ron=0, n_jobs=1)  # root directory
    # 5. fit grating equation
    kwargs_grating = dict(deg=(4, 10), nsigma=3, min_select=900)
    # 6. extract 1D spectrum
    kwargs_extract = dict(n_chunks=8, profile_oversample=10,
                          profile_smoothness=1e-2, num_sigma_clipping=20,
                          gain=1., ron=0, n_jobs=1)

    # SONG node list
    nodelist = ["delingha", "tenerife"]

    # thar template
    wave_temp = None
    thar_temp = None
    # load thar line list
    thar_line_list = None

    def set_parameters(self, node="delingha"):
        """ defaults to delingha parameters """
        assert node in self.nodelist
        if node == "delingha":
            # that's the default (2048x2048)
            pass
        if node == "tenerife":
            # for tenerife data (2088x2048)
            self.kwargs_read["trim"] = "[:, 21:2068]"

        # old comments
        # """ configuration for Song-China data """
        # # s.cfg.gain = {}
        # # s.cfg.trim['fits_section']=None
        # # s.cfg.rot90 = 0
        # """ configuration for Song-Tenerife data """
        # # s = Song._init_from_dir("/pool/song/sstenerife/star_spec/2017/20170314/night/raw/", verbose=False)
        # # s.cfg.trim['fits_section']="[:, 21:2068]" for tenerife data
        return

    def read_image(self, fp):
        """ read an image """
        if isinstance(fp, str):
            # single image
            return np.array(CCD.read(fp, **self.kwargs_read))
        else:
            # multiple images
            fp = list(fp)
            return np.array([self.read_image(_) for _ in fp])

    @staticmethod
    def read_header(fp):
        """ read an image header """
        return fits.getheader(fp)

    def proc_bias(self, fp):
        """ process bias """
        print("@Slit[{}]: processing bias ...".format(self.slit), end="")
        self.fps_bias = fp
        bias_data = self.read_image(fp)
        if bias_data.ndim == 3:
            self.bias = np.median(bias_data, axis=0)
        elif bias_data.ndim == 2:
            self.bias = bias_data
        print("Done!")
        return

    def proc_flat(self, fp):
        """ process bias """
        # 1. combine flat
        print("@Slit[{}]: processing flat ...".format(self.slit))
        self.fps_flat = fp
        flat_data = self.read_image(fp)
        if flat_data.ndim == 3:
            self.flat = np.median(flat_data, axis=0)
        elif flat_data.ndim == 2:
            self.flat = flat_data

        # 2. subtract bias
        flat_bias = self.flat - self.bias

        # 3. trace orders
        print("@Slit[{}]: tracing orders ...".format(self.slit))
        self.ap = Aperture.trace(flat_bias, method="naive", **self.kwargs_trace)

        # 3. subtract background
        print("@Slit[{}]: modeling background ...".format(self.slit))
        self.bg = self.ap.background(flat_bias, **self.kwargs_background_flat)
        flat_bias_bg = flat_bias - self.bg

        # 4. extract blaze & sensitivity
        print("@Slit[{}]: extracting blaze & sensitivity ...".format(self.slit), end="")
        self.blaze, self.sensitivity = self.ap.make_normflat(flat_bias_bg, **self.kwargs_normflat)
        print("Done!")
        return

    def proc_thar(self, fp, add=True, ipcprofile=None):
        if isinstance(fp, list):
            # multiple thar
            self.clear_tws()
            print("@Slit[{}]: cleared tws ...".format(self.slit))
            if ipcprofile is None:
                print("@Slit[{}]: processing {} thar sequentially ...".format(
                    self.slit, len(fp)))
                for fp_ in fp:
                    print("@Slit[{}]: processing {}...".format(self.slit, fp_))
                    self.proc_thar(fp_, add=True)
            else:
                rc = Client(profile=ipcprofile)
                print("@Slit[{}]: dispatching {} thar to ipcluster (profile={}, nproc={}) ...".format(
                    self.slit, len(fp), ipcprofile, len(rc.ids)))
                dv = rc.direct_view()
                dv.block = True
                dv.push({"this_slit": self})
                dv.scatter("fp", fp)
                dv.execute("this_slit.proc_thar(fp, add=True)")
                dv.execute("tws = this_slit.tws")
                self.tws = table.vstack(dv.gather("tws"))
                self.tws.sort("jdmid")
                dv.execute("%reset -f")
        else:
            # single thar

            # 1.read ThAr
            hdr = self.read_header(fp)
            # assert slit is correct
            assert hdr["SLIT"] == self.slit
            # thar data
            thar_data = self.read_image(fp)
            # thar time
            jdmid = hdr["JD-MID"]
            exptime = hdr["EXPTIME"]

            # 2.correct sensitivity
            thar_bg_sens = (thar_data - self.bias) / self.sensitivity
            # im_thar_denm_err = np.sqrt(np.abs(im_thar_denm)) / s.master_flats[slit]["norm"]

            # 3.extract ThAr spectrum
            rextr = self.ap.extract_all(thar_bg_sens, **self.kwargs_extract)
            thar_obs = rextr["spec_sum"]
            # thar_err = rextr["err_sum"]

            # 4.xcorrelate for initial wavelength guess
            wave_init = thar.corr_thar(self.wave_temp, self.thar_temp, thar_obs, maxshift=100)

            # 5. find thar lines
            tlines = thar.find_lines(wave_init, thar_obs, self.thar_line_list, npix_chunk=20)
            tlines = tlines[np.isfinite(tlines["line_x_ccf"])]

            # fit grating equation
            x = tlines["line_x_ccf"]  # line_x_ccf/line_x_gf
            y = tlines["order"]
            z = tlines["line"]

            pf1, pf2, indselect = thar.grating_equation(x, y, z, **self.kwargs_grating)
            tlines.add_column(table.Column(indselect, "indselect"))
            nlines = np.sum(indselect)
            # rms
            rms = np.std((pf2.predict(x, y) - z)[indselect])
            # predict wavelength solution
            nx, norder = thar_obs.shape
            mx, morder = np.meshgrid(np.arange(norder), np.arange(nx))
            wave_solu = pf2.predict(mx, morder)

            if add:
                # add this thar to list
                if fp in self.tws["fp"]:
                    # overwrite record
                    idx = np.int(np.where(fp == self.tws["fp"])[0])
                    self.tws.remove_row(idx)
                    self.tws.add_row([fp, jdmid, exptime, wave_init, wave_solu, tlines, nlines, rms, pf1, pf2])
                    self.tws.sort("jdmid")
                else:
                    self.tws.add_row([fp, jdmid, exptime, wave_init, wave_solu, tlines, nlines, rms, pf1, pf2])
                    self.tws.sort("jdmid")
            return

    def proc_star(self, fp, write=True, ipcprofile=None, prefix="tstar"):
        if isinstance(fp, list):
            # multiple star
            if ipcprofile is None:
                # sequentially
                print("@Slit[{}]: processing {} star sequentially ...".format(self.slit, len(fp)))
                results = []
                for fp_ in fp:
                    print("@Slit[{}]: processing {}...".format(self.slit, fp_))
                    results.append(self.proc_star(fp_))
                return results
            else:
                # parallel
                rc = Client(profile=ipcprofile)
                print("@Slit[{}]: dispatching {} star to ipcluster (profile={}, nproc={}) ...".format(
                    self.slit, len(fp), ipcprofile, len(rc.ids)))
                dv = rc.direct_view()
                dv.block = True
                dv.push({"this_slit": self, "prefix": prefix})
                dv.scatter("fp", fp)
                dv.execute("fps_out = this_slit.proc_star(fp, prefix=prefix)")
                # dv.execute()
                # dv.execute("tws = this_slit.tws")
                # self.tws = table.vstack(dv.gather("tws"))
                # self.tws.sort("jdmid")
                print("@Slit[{}]: Done!)".format(self.slit))
                print("saved to files:")
                print("========")
                for fp in dv.gather("fps_out"):
                    print(fp)
                print("========")
                dv.execute("%reset -f")
        else:
            # single star

            # 1.read star
            hdr = self.read_header(fp)
            # assert slit is correct
            assert hdr["SLIT"] == self.slit
            # star data
            star_data = self.read_image(fp)
            # star time
            jdmid = hdr["JD-MID"]
            exptime = hdr["EXPTIME"]
            bvc = hdr["BVC"]

            # 2.subtract bias & correct sensitivity
            star_bias_sens = (star_data - self.bias) / self.sensitivity

            # 3. subtract background
            bg = self.ap.background(star_bias_sens, **self.kwargs_background_star)
            star_bias_sens_bg = star_bias_sens - bg

            # 4.extract star spectrum
            rextr = self.ap.extract_all(star_bias_sens_bg, **self.kwargs_extract)
            # star_obs = rextr["spec_sum"]
            # star_err = rextr["err_sum"]

            # 5. append wavelength solution
            id_tws = np.argmin(np.abs(self.tws["jdmid"]-jdmid))
            rextr["wave"] = self.tws["wave_solu"][id_tws]
            rextr["wave_rms"] = self.tws["rms"][id_tws]
            rextr["blaze"] = self.blaze

            # 6. append info
            rextr["jdmid"] = jdmid
            rextr["exptime"] = exptime
            rextr["bvc"] = bvc

            # convert to table
            tstar = table.Table([rextr])
            tstar.meta = OrderedDict(hdr)

            # colname mapping
            tstar.rename_columns(['err_extr', 'err_extr1', 'err_extr2', 'err_sum', 'mask_extr',
                                  'spec_extr', 'spec_extr1', 'spec_extr2', 'spec_sum'],
                                 ['err', 'err1', 'err2', 'err_sum', 'mask',
                                  'flux', 'flux1', 'flux2', 'flux_sum'])

            if not write:
                return tstar
            else:
                assert os.path.exists(self.extdir)
                fp_output = "{}/{}_{}".format(self.extdir, prefix, os.path.basename(fp))
                print("@Slit[{}]: saving to {} ...".format(self.slit, fp_output))
                tstar.write(fp_output, ovebrwrite=True)
                return fp_output

    def __init__(self, slit=5, node="delingha", extdir="", ignore_warnings=True):
        self.slit = slit
        self.set_parameters(node=node)
        if extdir is not None:
            assert os.path.exists(extdir)
            self.extdir = extdir

        self.load_thar_template()
        self.clear_tws()

        # ignore warnings
        if ignore_warnings:
            self.ignore_warnings()
        return

    def __repr__(self):
        return "<Slit[{}] tws:{}>".format(self.slit, len(self.tws))

    def choose_tws(self, jd):
        pass

    def load_thar_template(self):
        # load thar template
        self.wave_temp = joblib.load("{}/calibration/wave_temp.dump".format(__path__[0]))
        self.thar_temp = joblib.load("{}/calibration/thar_temp.dump".format(__path__[0]))
        # thar_obs = joblib.load("{}/calibration/thar_obs.dump".format(__path__[0]))
        # load thar line list
        self.thar_line_list = joblib.load("{}/calibration/thar_line_list.dump".format(__path__[0]))
        return

    def clear_tws(self):
        """ clear ThAr Wavelength Solutions (tws) """
        self.tws = table.Table(data=[[], [], [], [], [], [], [], [], [], []],
                               names=["fp", "jdmid", "exptime", "wave_init", "wave_solu", "tlines", "nlines", "rms", "pf1", "pf2", ],
                               dtype=[object, object, object, object, object, object, object, object, object, object])
        return

    def ignore_warnings(self):
        warnings.filterwarnings("ignore")
        return

    def help(self):
        if self.node == "delingha":
            print(SLITINFO_DELINGHA)
        elif self.node == "tenerife":
            print(SLITINFO_TENERIFE)


