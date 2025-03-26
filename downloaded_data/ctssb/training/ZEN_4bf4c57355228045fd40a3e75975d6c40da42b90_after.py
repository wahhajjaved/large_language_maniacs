#em 2 nov 2015

import numpy as np
import sys
sys.path.insert(1, "./mccubed/")
import MCcubed as mc3
import matplotlib.pyplot as plt

def zen_init(data, pixels):
	"""
	This function does the initial calculations for pixel-level decorrelation.

	Parameters:
	-----------
	data: ndarray
	  3D float array of images

	pixels: ndarray
	  2D array coordinates of pixels to consider
	  EX: array([[ 0,  1],
				 [ 2,  3],
				 [ 4,  5],
				 [ 6,  7],
				 [ 8,  9],
				 [10, 11],
				 [12, 13],
				 [14, 15],
				 [16, 17],
				 [18, 19]])

	Returns:
	--------

	Example:
	--------
	>>> import numpy as np
	>>> data = np.arange(200).reshape(8,5,5)
	>>> pixels = [[1,2],[2,1],[2,2],[2,3],[3,2]]
	>>> res = zen_init(data,pixels)

	Modification History:
	---------------------
	2015-11-02 em	   Initial implementation
	2015-11-20 rchallen Generalized for any given pixels

	"""
	# Set number of frames and image dimensions
	nframes, ny, nx, nsets = np.shape(data)

	# Set number of pixels
	npix = len(pixels)
	
	# Initialize array for flux values of pixels
	p = np.zeros((nframes, npix))

	# Extract flux values from images
	for i in range(npix):
		for j in range(nframes):
			p[j,i] = data[j, pixels[i][0], pixels[i][1],0]

	# Initialize array for normalized flux of pixels
	phat = np.zeros(p.shape)
	
	# Remove astrophysics by normalizing
	for t in range(nframes):
		phat[t]	= p[t]/np.sum(p[t])

	# Calculate mean flux through all frames at each pixel
	pbar	= np.mean(phat, axis=0)

	# Difference from the mean flux
	dP	= phat - pbar

	return(phat, dP)

def eclipse(t, eclparams):
	"""
	This function calculates an eclipse following Mandel & Agol (2002)
	Adapted from mandelecl.c used in p6.

	Modification History
	--------------------
	2015-11-30 rchallen Adapted from C in mandelecl.c
	"""

	# Set parameter names
	midpt = eclparams[0]
	width = eclparams[1]
	depth = eclparams[2]
	t12   = eclparams[3]
	t34   = eclparams[4]
	flux  = eclparams[5]

	# If zero depth, set model to a flat line at 1
	if depth == 0:
		y = np.ones(t.size)
		return y

	# Beginning of eclipse
	t1 = midpt - width/2

	# End of eclipse
	if t1 + t12 < midpt:
		t2 = t1+t12
	else:
		t2 = midpt

	t4 = midpt + width / 2

	if t4 - t34 > midpt:
		t3 = t4 - t34
	else:
		t3 = midpt

	p = np.sqrt(np.abs(depth)) * (depth/np.abs(depth))

	dims = t.size
	
	y = np.ones(dims)

	# Calculate ingress/egress
	for i in range(dims):
		y[i] = 1
		if t[i] >= t2 and t[i] <= t3:
			y[i] = 1 - depth

		elif p != 0:
			if t[i] >= t1 and t[i] <= t2:
				z  = -2 * p * (t[i] - t1) / t12 + 1 + p
				k0 = np.arccos((p**2 + z**2 - 1) / (2 * p * z))
				k1 = np.arccos((1 - p**2 + z**2) / (2 * z))
				y[i] = 1 - depth/np.abs(depth)/np.pi * \
				  (p**2 * k0 + k1 - np.sqrt((4 * z**2 - (1 + z**2 - p**2)**2)/4))

			elif t[i] > t3 and t[i] < t4:
				z  = 2 * p * (t[i] - t3) / t34 + 1 - p
				k0 = np.arccos((p**2 + z**2 - 1) / (2 * p * z))
				k1 = np.arccos((1 - p**2 + z**2) / (2 * z))
				y[i] = 1 - depth/np.abs(depth)/np.pi * \
				  (p**2 * k0 + k1 - np.sqrt((4 * z**2 - (1 + z**2 - p**2)**2)/4))

		#y[i] *= flux

	return y

def zen(par, x, phat, npix):
	"""
	Zen function.

	Parameters:
	-----------
	par: ndarray
	  Zen parameters, eclipse parameters, ramp parameters
	x: ndarray
	  Locations to evaluate eclipse model
	npix: int
	  

	Returns:
	--------
	y: ndarray
	  Model evaluated at x

	Modification History:
	---------------------
	2015-11-02 em	   Initial implementation.
	2015-11-20 rchallen Adaptation for use with MCcubed

	Notes:
	------
	Only allows for quadratic ramp functions
	"""

	# PLD term in the model
	PLD = 0
	
	# Calculate eclipse model using parameters
	# FINDME: remove hard-coded number of ramp params
	eclparams = par[npix:-3]
	eclmodel = eclipse(x, eclparams)
	
	# Calculate the sum of the flux from all considered pixels
	for i in range(npix):
		PLD += par[i]*phat[:,i]

	# Calculate the model
	# FINDME: allow for general ramp function
	#y = ((1 + PLD) + (eclmodel - 1) + (par[-3] + par[-2]*x + par[-1]*x**2))*eclparams[-1]

	y = PLD + eclparams[-1] * (eclmodel - 1) + (par[-3] + par[-2]*x + par[-1]*x**2)
	return y

def bindata(x, y, ppb, yerr=None):
    nbin = int(len(x)/ppb)

    binx = np.zeros(nbin)
    biny = np.zeros(nbin)

    if type(yerr) != type(None):
        binyerr = np.zeros(nbin)

    for i in range(nbin):
        binx[i] = np.mean(x[i*ppb:(i+1)*ppb])
        biny[i] = np.mean(y[i*ppb:(i+1)*ppb])
        if type(yerr) != type(None):
            binyerr[i] = np.mean(yerr[i*ppb:(i+1)*ppb])/ppb**.5
            #binyerr[i] = (np.sum(yerr[i*ppb:(i+1)*ppb]**2))**.5/ppb**

    if type(yerr) != type(None):
        return binx, biny, binyerr
    else:
        return binx, biny

def flux(phase, phot, phat):
    '''
    Find the stellar flux by chi-squared minimization.
    '''
    npix  = phat.shape[1]
    ndata = phat.shape[0]

    searchrange = np.linspace(0.5-0.01, 0.5+0.01,100)

    bestres = 1e300
    
    for i in searchrange:
      eclparams = [i, 0.1, 1, 0.0006, 0.0006, 1]
      ecl = zf.eclipse(phase, eclparams)
      xx = np.c_[phat, ecl-1, phase, phase**2]
      x, res, rank, s = np.linalg.lstsq(xx, phot)
      if res < bestres:
        bestres = res
        bestecl = ecl
        bestx   = x
        bestxx  = xx
    print(res)

    sol = np.dot(bestxx, bestx)

    flux = np.sum(bestx[:npix])

    return flux
    
def read_MCMC_out(MCfile):
    """
    Read the MCMC output log file. Extract the best fitting parameters.

    Taken from BART's bestFit.py at
    https://github.com/exosports/BART
    """
    # Open file to read
    f = open(MCfile, 'r')
    lines = np.asarray(f.readlines())
    f.close() 

    # Find where the data starts and ends:
    for ini in np.arange(len(lines)):
        if lines[ini].startswith(' Best-fit params'):
            break
    ini += 1
    end = ini
    for end in np.arange(ini, len(lines)):
        if lines[end].strip() == "":
            break

    # Read data:
    bestP = np.zeros(end-ini, np.double)
    uncer = np.zeros(end-ini, np.double)
    for i in np.arange(ini, end):
        parvalues = lines[i].split()
        bestP[i-ini] = parvalues[0]
        uncer[i-ini] = parvalues[1]

    return bestP, uncer

def get_params(bestP, stepsize, params):
    """
    Get correct number of all parameters from stepsize

    Original code taken from BART's bestFit.py at
    https://github.com/exosports/BART
    """
    j = 0
    allParams = np.zeros(len(stepsize))
    for i in np.arange(len(stepsize)):
        if stepsize[i] > 0.0:
            allParams[i] = bestP[j]
            j +=1
        else:
            allParams[i] = params[i]

    # Loop again to fill in where we have negative step size
    for i in np.arange(len(stepsize)):
        if stepsize[i] < 0.0:
            allParams[i] = allParams[int(-stepsize[i]-1)]
            
    return allParams

def reschisq(y, x, yerr):
    '''
    Little function to calculate chisq of a log data set against
    a line with slope -0.5. Used to check residual binning.
    '''
    m = -0.5
    line = 10.0**(np.log10(y[0]) + m * np.log10(x))
    diff = y - line
    # We use median of the error here just because the first implementation
    # of PLD does. It is probably better to weight each point
    # individually (and in fact, weighting them equally should not
    # have any effect).
    chisq = np.sum(diff**2/np.median(yerr)**2)
    # Actually fit a line and find the slope. This will be used later
    # to discard some fits
    fit = np.polyfit(np.log10(x), np.log10(y), 1)
    slope = fit[0]
    return chisq, slope

def do_bin(bintry, phasegood, phatgood, phot, photerr,
           params, npix, stepsize, pmin, pmax, chisqarray,
           chislope, photind, centind, nphot, plot=False):
    '''
    Function to be launched with multiprocessing.

    Notes
    -----
    This function modifies (fills in) the passed chisqarray variable.
    It returns nothing because this function is meant to be used
    with multiprocessing.
    '''
    
    # Optimize bin size
    print("Optimizing bin size.")
    for i in range(len(bintry)):
        #print("Least-squares optimization for " + str(bintry[i])
        #      + " points per bin.")

        # Bin the phase and phat
        for j in range(npix):
            if j == 0:
                binphase,     binphat = bindata(phasegood,
                                                phatgood[:,j],
                                                bintry[i])
            else:
                binphase, tempbinphat = bindata(phasegood,
                                                phatgood[:,j],
                                                bintry[i])
                binphat = np.column_stack((binphat, tempbinphat))
                # Bin the photometry and error
                # Phase is binned again but is identical to
                # the previously binned phase.
        binphase, binphot, binphoterr = bindata(phasegood, phot, bintry[i], yerr=photerr)

        # Normalize
        photnorm    = phot    / phot.mean()
        photerrnorm = photerr / phot.mean()

        binphotnorm    = binphot    / binphot.mean()
        binphoterrnorm = binphoterr / binphot.mean()

        # Number of parameters we are fitting
        # This loop removes fixed parameters from the
        # count
        nparam = len(stepsize)
        for ss in stepsize:
            if ss <= 0:
                nparam -= 1

        # Minimize chi-squared for this bin size
        indparams = [binphase, binphat, npix]
        chisq, fitbestp, dummy, dummy = mc3.fit.modelfit(params, zen,
                                                         binphotnorm,
                                                         binphoterrnorm,
                                                         indparams,
                                                         stepsize,
                                                         pmin, pmax)

        # Calculate model on unbinned data from parameters of the
        # chi-squared minimization with this bin size. Calculate
        # residuals for binning
        sdnr        = []
        binlevel    = []
        err         = []
        resppb      = 1
        unbinnedres = photnorm - zen(fitbestp, phasegood, phatgood, npix)
        resbin = len(phasegood)
        num    = len(unbinnedres)
        sigma = np.std(unbinnedres)   * np.sqrt(num   /(num   -nparam))
        
        # Bin the residuals, calculate SDNR of binned residuals. Do this
        # until you are binning to <= 16 points remaining.
        while resbin > 16:
            xrem = num - resppb * resbin
            # This part is gross. Need to clean up
            dummy, binnedres = bindata(phasegood[xrem:],
                                       unbinnedres[xrem:],
                                       resppb)
            sdnr.append(np.std(binnedres) * np.sqrt(resbin/(resbin-nparam)))
            binlevel.append(resppb)
            ebar  = sigma/np.sqrt(2 * resbin)
            err.append(ebar)
            resppb *= 2
            resbin = int(num/resppb)

        sdnr[0] = sigma
        err[0]  = sigma/np.sqrt(2*num)
        # Calculate chisquared of the various SDNR wrt line of slope -0.5
        # passing through the SDNR of the unbinned residuals
        # Record chisquared
        sdnr     = np.asarray(sdnr)
        binlevel = np.asarray(binlevel)
        sdnrchisq, slope = reschisq(sdnr, binlevel, err)

        # Some diagnostic plotting
        if plot == True:
            ax = plt.subplot(111)
            ax.set_xscale('log')
            ax.set_yscale('log')
            plt.errorbar(binlevel, sdnr, yerr=err, fmt='o')
            plt.plot(binlevel, 10**(np.log10(sdnr[0]) + (-.5) * np.log10(binlevel)))
            plt.show()
            
        print(" Ap: "    + str(photind) +
              " Cent: "  + str(centind) +
              " Bin: "   + str(i)       +
              " Chisq: " + str(sdnrchisq))
        chisqarray[i + len(bintry) * photind + len(bintry) * nphot * centind] = sdnrchisq
        chislope[  i + len(bintry) * photind + len(bintry) * nphot * centind] = slope
