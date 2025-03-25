from pylab import *
from Functions import *
import pandas as pd

name = ''


def loadme(name):
    '''
    arguments:
    name = the name of the folder
    -----
    returns:
    data, parameters_dict, on_off, offset_list
    '''
    try:
        data = pd.read_csv(str(name) + 'data_frame.csv', index_col=0)
        print 'data frame loaded'
        parameters_dict = pickle.load(
            open(str(name) + 'spline_parameters' + ".p", "rb"))
        print 'parameters_dict loaded'
        on_off = save_suhtters(name)
        print 'on off loaded'
        offset_list = [[5, 5] for i in range(len(on_off))]  # [[5,56],[10,56]]
        print 'offset_list done'
    except:
        Exception
        print'not found'
        data = None
        parameters_dict = None
    return data, parameters_dict, on_off, offset_list


def do(data, structure, parameters_dict, name, res=False):
    '''
    load data frame and plot shit.
    -------
    input:
    data : the dataframe to be plotted
    structure : string to select WZ,ZB,TW
    parameters_dict: the parameters of the spline
    '''
    fig, ax = subplots(3, 1, figsize=(30, 20), sharex=True)

    on_off = save_suhtters(name)

    data_temp = data

    offset_list = [[5, 5] for i in range(len(on_off))]  # [[5,56],[10,56]]

    x = data.index
    y = data_temp['Int_' + str(structure)]
    xs, ys, d_ys, dd_ys = spline_do(
        x, y, ax, n=3, s=parameters_dict[str(structure)], k=3, plot=False)

    ax[0].plot(x, y, '.', label=y.name)
    ax[0].plot(xs, ys, '-', label=y.name + 'Spline')
    ax2 = ax[0].twinx()

    ax2.plot(xs, d_ys, '--', label=y.name + '1st d erivative')
    ax2.set_ylabel('Normalized intensity (a.u)')
    ax2.legend()
    plot_shutters(on_off, data_temp, ax,
                  offset=offset_list, ls='--', color='k')

    y = data_temp.NIG

    ax[1].plot(x[data.NIG != 1], y[data.NIG != 1], label=y.name)

    ax[1].set_ylabel('Ion Gauge Pressure (Pa)')
    y = data_temp['FWHM_x_' + str(structure)]
    ax[2].plot(x, y[data_temp.FWHM_x_WZ != 0], label=y.name)
    y = data_temp['FWHM_y_' + str(structure)]
    ax[2].plot(x, y[data_temp.FWHM_y_WZ != 0], label=y.name)
    ax[2].set_ylabel('Normalized intensity (a.u)')
    [j.legend(loc=0) for j in ax]
    ax[2].set_xlabel('Time (s)')
    return fig, ax


def do_derivatives(data, parameters_dict, name, shutter=False):
    fig, ax = subplots()
    on_off = save_suhtters(name)
    data_temp = data
    offset_list = [[5, 5] for i in range(len(on_off))]  # [[5,56],[10,56]]

    x = data.index
    # WZ
    y = data_temp.Int_WZ
    xs, ys, d_ys, dd_ys = spline_do(
        x, y, [ax], n=3, s=parameters_dict['WZ'], k=3, plot=False)

    ax.plot(xs, norm(d_ys), '--', label=y.name + '1st d erivative')
    ax.set_ylabel('Normalized intensity (a.u)')
    ax.legend()
    if shutter:
        plot_shutters(on_off, data_temp, [ax],
                      offset=offset_list, ls='--', color='k')
    # now to ZV
    y = data_temp.Int_TW
    xs, ys, d_ys, dd_ys = spline_do(x, y,
                                    [ax], n=3,
                                    s=parameters_dict['TW'],
                                    k=3, plot=False)
    ax.plot(xs, norm(d_ys), '--', label=y.name + '1st d erivative')
    ax.set_ylabel('Normalized intensity (a.u)')
    ax.legend()

    return fig, ax


def create_par_dict():
    parameters_dict = {}
    structures = ['WZ', 'TW', 'ZB']
    for i in structures:
        value = raw_input('Insert spline value for %s: ' % (i))
        parameters_dict[i] = float(value)
    print 'done'
    return parameters_dict


def do_diff_derivatives(data, parameters_dict, structure, name, shutter=False, nig=True, sum_on=False, shade=True, **kwargs):
    '''
    Perform the difference of the derivatives I_WZ  and I[structure]
    of the spline fitted data with  the parameters specified
    in the parameters_dict.
    '''
    fig, ax = subplots(**kwargs)

    on_off = save_suhtters(name)

    data_temp = data

    offset_list = [[5, 5] for i in range(len(on_off))]  # [[5,56],[10,56]]

    x = data.index
    y = data_temp.Int_WZ
    xs_WZ, ys_WZ, d_ys_WZ, dd_ys_WZ = spline_do(
        x, y, [ax], n=3, s=parameters_dict['WZ'], k=3, plot=False)
    if shutter:
        plot_shutters(on_off, data_temp, [ax],
                      offset=offset_list, ls='--', color='k')
    y_wz = array(y)
    # now to ZV
    y = data_temp['Int_' + str(structure)]
    xs_TW, ys_TW, d_ys_TW, dd_ys_TW = spline_do(
        x, y, [ax], n=3,
        s=parameters_dict[structure], k=3, plot=False)
    diff = (norm(d_ys_WZ) - norm(d_ys_TW))  # / (d_ys_WZ + d_ys_TW )
    summed = d_ys_WZ + d_ys_TW
    summ_int = y_wz + array(y)
    # to create nice legend
    line1, = ax.plot(xs_TW, diff, c='#00A0B0',
                     label=r'$I{\prime}_{WZ} - I{\prime}_{%s}$' % (structure))
    if nig:
        ax2 = ax.twinx()
        ax2.set_ylabel('Pressure (Pa)')
        # to create nice legend
        line2, = ax2.plot(x[data_temp.NIG != 1],
                          data_temp.NIG[data_temp.NIG != 1],
                          c='#EB6841', label='NIG')
        ax2.yaxis.label.set_color(line2.get_color())  # color the label
        ax2.tick_params(axis='y', colors=line2.get_color())
        lines = [line1, line2]  # to create nice legend
        ax.legend(lines, [l.get_label()
                  for l in lines], loc=0)  # to create nice legend
    # if not nig:
    #     ax.legend(loc=0)

    if sum_on:
        ax3 = ax.twinx()
        ax3.set_ylabel(' intensity (a.u)')
        line2, = ax3.plot(xs_TW, summ_int,
                          '.',
                          c='orange',
                          label=r'$I_{WZ} + I_{%s}$' % (structure))
        lines = [line1, line2]  # to create nice legend
        ax.legend(lines, [l.get_label()
                           for l in lines], loc=3)  # to create nice legend
    if shade:
        for on, off in zip(on_off[:-1:2], on_off[1::2]):
            on = on + data.index.values.min()
            off = off + data.index.values.min()
            ax.add_patch(Rectangle((on, -1), off - on, 2, facecolor="grey"))
    ax.annotate('Open',
                xy=(203, .85),
                xytext = (0, 0), fontsize=10,
                weight= 'semibold', color='white',
                horizontalalignment='center', rotation=45,
                bbox = dict(fc='k', alpha=.0),
                textcoords = 'offset points')
    ax.annotate('''In
shutter:''',
                xy=(135, .71),
                xytext = (0, 0), fontsize=10,
                weight= 'semibold', color='black',
                horizontalalignment='center',
                bbox = dict(fc='k', alpha=.0),
                textcoords = 'offset points')
    ax.annotate('Close',
                xy=(175, .85),
                xytext = (0, 0), fontsize=11,
                weight= 'semibold', color= '#353535',
                horizontalalignment='center', rotation=45,
                bbox = dict(fc='k', alpha=.0),
                textcoords = 'offset points')
    ax.set_ylabel('Normalized intensity (a.u)')
    ax.set_ylim(-1, 1)
    return fig, ax


def shade(on_off, ax):
    for on, off in zip(on_off[:-1:2], on_off[1::2]):
            on = on + data.index.values.min()
            off = off + data.index.values.min()
            ax.add_patch(Rectangle((on, -1), off - on, 2, facecolor="grey"))
