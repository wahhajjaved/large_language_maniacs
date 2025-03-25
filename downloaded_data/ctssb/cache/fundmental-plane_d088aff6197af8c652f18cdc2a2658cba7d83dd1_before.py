import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from astropy.modeling import models, fitting
import pickle
from position import Location
from javelin.zylc import get_data
from javelin.lcmodel import Cont_Model, Rmap_Model


def read_flux(rmid, band):
    f = open(Location.project_loca + "result/flux_of_line/" + str(rmid) + "/" +
             str(band) + ".pkl", "rb")
    dic = pickle.load(f)
    return dic


def read_re(rmid, band):
    f = open(Location.project_loca + "result/flux_of_line/" + str(rmid) + "/" +
             str(band) + "_error.pkl", "rb")
    dic = pickle.load(f)
    return dic


def lc_gene(rmid):
    o3_flux = read_flux(rmid, "O3")
    o3_error = read_re(rmid, "O3")
    band_list = ["Hbetab", "O3", "cont"]
    for each in band_list:
        flux = read_flux(rmid, each)
        error = read_re(rmid, each)
        flux_key = set(flux.keys())
        error_key = set(error.keys())
        all_mjd = flux_key.intersection(error_key)
        mjd_list = sorted(all_mjd)
        lc_file = open(Location.project_loca + "result/light_curve/" +
                       str(rmid) + "/" + str(each) + ".txt", "w")
        for each_day in mjd_list:
            try:
                flux_each = flux[each_day] / o3_flux[each_day]
                error_each = abs(error[each_day] * flux[each_day] * 
                                 o3_flux[each_day] - o3_error[each_day] * 
                                 o3_flux[each_day] * flux[each_day]) / \
                    (flux[each_day] ** 2.0)
            except Exception:
                continue
            lc_file.write(str(each_day) + "    " + str(flux_each) + "    " +
                          str(error_each) + "\n")
        lc_file.close()


def rm_single(rmid, nwalker, nchain, nburn, fig_out):
    # Input and output data position and name
    file_con = Location.project_loca + "result/light_curve/" + str(rmid) + \
        "/cont.txt"
    file_hbeta = Location.project_loca + "result/light_curve/" + str(rmid) + \
        "/Hbetab.txt"
    lc_plot = Location.project_loca + "result/light_curve/" + str(rmid) + \
        "/lightcurve"
    data_out = Location.project_loca + "result/light_curve/" + str(rmid) + \
        "/cont-hbeta.txt"
    last_mcmc = Location.project_loca + "result/light_curve/" + str(rmid) + \
        "/last_mcmc"
    result = Location.project_loca + "result/light_curve/" + str(rmid) + \
        "/result.pkl"
    # Fit continuum
    c = get_data([file_con])
    cmod = Cont_Model(c)
    cmod.do_mcmc(threads=100, nwalkers=nwalker, nchain=nchain, nburn=nburn)
    # Do mcmc
    cy = get_data([file_con, file_hbeta], names=["Continuum", "Hbeta"])
    cy.plot(figout=lc_plot, figext="png")
    cymod = Rmap_Model(cy)
    cymod.do_mcmc(conthpd=cmod.hpd, threads=100, fchain=data_out,
                  nwalkers=nwalker, nchain=2.0 * nchain, nburn=2.0 * nburn)
    # Output mcmc result
    cymod.show_hist(figout=fig_out, figext="png")
    cypred = cymod.do_pred()
    cypred.plot(set_pred=True, obs=cy, figout=last_mcmc, figext="png")
    # Fitting lag and error
    num = np.histogram(cymod.flatchain[:, 1] / np.log(10.0), 100)
    num_x = np.array([(num[1][i] + num[1][i+1]) * 0.5
                      for i in xrange(len(num[1]) - 1)])
    err = np.histogram(cymod.flatchain[:, 0] / np.log(10.0), 100)
    err_x = np.array([(err[1][i] + err[1][i+1]) * 0.5
                      for i in xrange(len(err[1]) - 1)])
    num_func = models.Gaussian1D(max(num[0]), np.mean(num[1]), 1.0)
    err_func = models.Gaussian1D(max(err[0]), np.mean(err[1]), 1.0)
    fitter = fitting.LevMarLSQFitter()
    num_fit = fitter(num_func, num_x, num[0])
    fig = plt.figure()
    plt.hist(cymod.flatchain[:, 1] / np.log(10.0), 100)
    plt.plot(num[1], num_fit(num[1]))
    fig.savefig(fig_out + "-num.png")
    plt.close()
    num_res = num_fit.parameters
    err_fit = fitter(err_func, err_x, err[0])
    fig = plt.figure()
    plt.hist(cymod.flatchain[:, 0] / np.log(10.0), 100)
    plt.plot(err[1], err_fit(err[1]))
    fig.savefig(fig_out + "-err.png")
    plt.close()
    err_res = err_fit.parameters
    # Saving final result
    file_out = open(result, "wb")
    pickle.dump([num_res, err_res], file_out)
    file_out.close()


def rm(rmid, nwalker=500, nchain=250, nburn=250, ** kwargs):
    print("Begin rm for " + str(rmid))
    os.chdir(Location.project_loca + "result")
    try:
        os.mkdir("light_curve")
    except OSError:
        pass
    os.chdir("light_curve")
    try:
        os.mkdir(str(rmid))
    except OSError:
        pass
    try:
        lc_gene(rmid)
        fig_out = Location.project_loca + "result/light_curve/" + str(rmid) + \
            "/cont-hbeta"
        if "outname" in kwargs:
            fig_out = fig_out + "-" + str(kwargs["outname"])
        rm_single(rmid, nwalker, nchain, nburn, fig_out)
        print("    Finished")
    except Exception as reason:
        print("    Failed because of: " + str(reason))
