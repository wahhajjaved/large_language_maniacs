from __future__ import division, print_function, absolute_import
import numpy as np
import scipy.io as sio
# import matplotlib
# matplotlib.use('Agg') # Must be before importing matplotlib.pyplot or pylab!
import matplotlib.pyplot as plt
import os
from datetime import datetime
import im3D.sdf.inplace
import im3D.smoothing.inplace
from imseg.regions import init_regions, update_regions
from imseg.update_sdf import update_sdf


def require_array(a, dtype=None):
    if a is not None:
        return np.array(a, dtype, copy=False, ndmin=1)


def prep_dir(path):
    dirname = os.path.dirname(path)
    if dirname != '' and not os.path.exists(dirname):
        os.makedirs(dirname)


def proc_num(value):
    """
    Input string.
    If string is numeric, convert to numeric types (float or int),
    otherwise return the string as it is.
    """
    try:
        value = float(value)
        if value.is_integer():
            value = int(value)
    except ValueError:
        pass
    return value


def proc_list(value):
    """
    Convert string to list.
    """
    if ',' in value:
        value = [proc_num(v.strip()) for v in value.split(',')]
    return value


def proc_slice(value):
    """
    Convert string to slice object.
    """
    if (type(value) is str) and (':' in value):
        value = slice(*[int(x) if x != '' else None for x in value.split(':')])
    return value


def read_input(filename, comment='#', sep='='):
    """
    Read input from a text file into a dictionary.
    """
    kwargs = {}
    with open(filename, 'r') as f:
        s = f.readlines()
        for line in s:
            line = line.split(comment, 1)[0].strip() # Remove comment
            if line:
                key, value = line.split(sep, 1)
                key = key.strip()
                value = value.strip()
                # List type
                if ',' in value:
                    value = [proc_num(v.strip()) for v in value.split(',')]
                # Numeric type
                else:
                    value = proc_num(value)
                kwargs[key] = value
    return kwargs


def dump_file(infile, outfile, verbose=True, write_time=True):
    prep_dir(outfile)
    if verbose:
        print(u'{0:s} -> {0:s}'.format(infile, outfile))
    with open(infile, 'r') as fin, open(outfile, 'a') as fout:
        if write_time:
            fout.write(u'* * * {0:s} * * *'.format(datetime.now()))
        fout.writelines(fin.readlines())


class ImSeg(object):
    def __init__(self, im, **kwargs):
        self.im = np.asarray(im)
        self.dtype = self.im.dtype
        self.kwargs = kwargs
        print('* * * Keyword Arguments: * * *')
        print(self.kwargs)

    def initialize(self):
        """
        Initialize the segmentation.
        :param thresholds:
        :return:
        """
        # Initialize variables
        self.thresholds = require_array(self.kwargs.get('thresholds'), dtype=self.dtype)
        self.nthresh = np.ndim(self.thresholds)
        self.sdf = np.empty((self.nthresh, ) + self.im.shape, dtype=self.dtype)
        self.im_ave = np.empty_like(self.im, dtype=self.dtype)
        self.im_error = np.empty_like(self.im, dtype=self.dtype)
        self.iter_count = 0

        # Initialize regions
        print('Initializing SDF and calculating im_ave & im_error ...')
        init_regions(self.im, self.thresholds, self.im_ave, self.im_error, self.sdf)
        
        # Reinitialize SDF
        print('Reinitializing SDF ...')
        for i in xrange(self.nthresh):
            im3D.sdf.inplace.reinit(self.sdf[i], self.sdf[i], 
                                    dt=self.kwargs['init_reinit_dt'],
                                    niter=self.kwargs['init_reinit_niter'],
                                    subcell=self.kwargs['init_reinit_subcell'],
                                    WENO=self.kwargs['init_reinit_weno'],
                                    verbose=True)

    def assertion(self):
        assert self.im_error.shape == self.im.shape
        assert self.im_ave.shape == self.im.shape
        assert self.sdf.shape == (self.nthresh,) + self.im.shape

    def iterate(self, niter=1):
        for i in xrange(niter):
            print('Starting iteration %d' % (self.iter_count + 1))
            print('Smoothing interface of im_ave ...')
            im3D.smoothing.inplace.ds(self.im_ave, self.im_ave, 
                                      it=self.kwargs['ave_diff_niter'], 
                                      dt=self.kwargs['ave_diff_dt'], 
                                      D=self.kwargs['ave_diff_coef'])
            print('Smoothing im_error by diffusion ...')
            im3D.smoothing.inplace.ds(self.im_error, self.im_error, 
                                      it=self.kwargs['err_diff_niter'], 
                                      dt=self.kwargs['err_diff_dt'], 
                                      D=self.kwargs['err_diff_coef'])
            print('Updating SDF using im_error ...')
            update_sdf(self.sdf, self.im_error, self.kwargs['beta'])
            print('Smoothing SDF by diffusion ...')
            for i in xrange(self.nthresh):
                im3D.smoothing.inplace.ds(self.sdf[i], self.sdf[i], 
                                          it=self.kwargs['sdf_diff_niter'], 
                                          dt=self.kwargs['sdf_diff_dt'], 
                                          D=self.kwargs['sdf_diff_coef'])
            
            # Reinitialize SDF
            print('Reinitializing SDF ...')
            for i in xrange(self.nthresh):
                im3D.sdf.inplace.reinit(self.sdf[i], self.sdf[i], 
                                        dt=self.kwargs['reinit_dt'],
                                        niter=self.kwargs['reinit_niter'],
                                        subcell=self.kwargs['reinit_subcell'],
                                        WENO=self.kwargs['reinit_weno'],
                                        verbose=True)
            
            # Calculating means and error with the updated SDF
            print('Calculating means and error with the updated SDF ...')
            update_regions(self.im, self.sdf, self.im_ave, self.im_error)
            
            # Increase iteration counter
            self.iter_count += 1

    def plot_contour(self, im_slice=Ellipsis, outdir=None, show=True):
        for i in xrange(self.nthresh):
            plt.figure('contour-%d_iter_%d' % (i+1, self.iter_count))
            plt.title('contour-%d, iteration %d' % (i+1, self.iter_count))
            plt.imshow(self.im[im_slice], interpolation='nearest', cmap='gray')
            plt.contour(self.sdf[i][im_slice], levels=[0], colors='r')
            if outdir is not None:
                plt.savefig(outdir + '/contour-%d_iter_%d' % (i+1, self.iter_count))
        if show is True:
            if outdir is None:
                plt.show()

    def plot(self, im_slice=Ellipsis, outdir=None):
        print('Plotting data ...')
        plt.figure('im_ave')
        plt.title('im_ave, iteration %d' % self.iter_count)
        plt.imshow(self.im_ave[im_slice])
        plt.colorbar()
        if outdir is not None:
            prep_dir(outdir)
            plt.savefig(outdir + 'im_ave_iter_%d' % self.iter_count)
        plt.figure('im_error')
        plt.title('im_error, iteration %d' % self.iter_count)
        plt.imshow(self.im_error[im_slice])
        plt.colorbar()
        if outdir is not None:
            plt.savefig(outdir + 'im_error_iter_%d' % self.iter_count)
        for i in xrange(self.nthresh):
            plt.figure('SDF-%d' % (i + 1))
            plt.title('SDF-%d, iteration %d' % (i + 1, self.iter_count))
            plt.imshow(self.sdf[i][im_slice])
            plt.colorbar()
            if outdir is not None:
                plt.savefig(outdir + 'SDF-%d_iter_%d' % (i + 1, self.iter_count))
        self.plot_contour(im_slice=im_slice, outdir=outdir, show=False)
        if outdir is None:
            plt.show()
        else:
            plt.close('all')

    def write_paras(self, outpath='./parameters.txt'):
        prep_dir(outpath)
        print('Writing parameters into file %s ...' % outpath)
        f = open(outpath, 'w')
        f.writelines(dump_dict(self.kwargs))
        f.close()

    def save(self, prefix='imseg_iter_', fmt='bin'):
        prep_dir(prefix)
        outname = '%s%d.%s' % (prefix, self.iter_count, fmt)
        print('Writing output to file %s ...' % outname)    
        if fmt == 'mat':
            sio.savemat(outname,
                        {'thresholds':self.thresholds,
                        'sdf':self.sdf,
                        'iter_count':self.iter_count})
        elif fmt == 'npz':
            np.savez(outname,
                     thresholds=self.thresholds,
                     sdf=self.sdf,
                     iter_count=self.iter_count)
        elif fmt == 'bin':
            self.sdf.tofile(outname)
        else:
            raise KeyError('File format not understood!')

    def load(self, path2file, dtype='float32', iter_count=None, thresholds=None):
        fmt = os.path.splitext(path2file)[-1]
        print('Loading segmentation from file %s ...' % path2file)
        if fmt == 'npz':
            a = np.load(path2file)
            self.thresholds = a['thresholds']
            self.iter_count = a['iter_count']
            self.sdf = a['sdf']
        elif fmt == 'mat':
            a = sio.loadmat(path2file)
            self.thresholds = a['thresholds']
            self.iter_count = a['iter_count']
            self.sdf = a['sdf']
        elif fmt == 'bin':
            self.thresholds = thresholds
            self.sdf = np.fromfile(path2file, dtype=dtype).reshape(thresholds.shape+self.im.shape)
            self.iter_count = iter_count
        else:
            raise KeyError('File format not understood!')
        # Reinitialize variables
        self.nthresh = np.ndim(self.thresholds)
        self.im_ave = np.empty_like(self.im, dtype=self.dtype)
        self.im_error = np.empty_like(self.im, dtype=self.dtype)
        print('Calculating means and error with the loaded SDF ...')
        update_regions(self.im, self.sdf, self.im_ave, self.im_error)
        print('Done!')


def dump_dict(d, indent=0):
    out = ''
    for key, value in d.iteritems():
        out += '\t' * indent + str(key) + '\n'
        if isinstance(value, dict):
            out += dump_dict(value, indent + 1)
        else:
            out += '\t' * (indent + 1) + str(value) + '\n'
    return out


del absolute_import
del print_function
del division



