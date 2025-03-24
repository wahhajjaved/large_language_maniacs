usage="""a module to compute basic statistics of skymaps"""

import healpy as hp
import numpy as np


#=================================================
#
# general helper methods
#
#=================================================
def cos_dtheta(theta1, phi1, theta2, phi2):
	"""
	computes the angular separation between two points
	support arrays assuming they all have the same shape
	"""
	return np.cos(theta1)*np.cos(theta2) + np.sin(theta1)*np.sin(theta2)*np.cos(phi1-phi2)

#=================================================
#
# methods involving manipulating a posterior
#
#=================================================
def rankmap(posterior, npix=None):
        """
        converts a posterior into a rank map. Small ranks correspond to large posterior weight
        WARNING: rankmaps do not sum to unity!
        """
	if not npix:
	        npix = len(posterior)
        rankmap = np.empty(npix,int)
        rankmap[posterior.argsort()] = np.arange(npix)[::-1]
        return rankmap

###
def resample(posterior, new_nside, nest=False):
	"""
	creates a new posterior with len=hp.nside2npix(new_nside)
		if new_nside > nside: we assign each new pixel an equal fraction of the parent pixel's value
		if new_nside < nside: we assign each new pixel the sum of the contained pixels
	"""
	return hp.ud_grade(posterior, new_nside, power=-2)

#	npix = len(posterior)
#	new_npix = hp.nside2npix(new_nside)
#	if npix == new_npix:
#		return posterior
#	elif npix < new_npix:
#		### upsample by assiging a fraction of the probability to each new pixel
#		nside = hp.npix2nside(npix)
#		new_t, new_p = hp.pix2ang(new_nside, np.arange(new_npix), nest=nest) # location of new pixels
#		return posterior[hp.ang2pix(nside, new_t, new_p, nest=nest)]*1.0*npix/new_npix
#	else: #npix > new_npix
#		### downsample by assigning the sum of containted probability to each new pixel
#                nside = hp.npix2nside(npix)
#		new_posterior = np.zeros((new_npix,))
#		for ipix, post in enumerate(posterior): ### iterate over old posterior and add contributions to new posterior
#			t, p = hp.pix2ang(nside, ipix)
#			new_posterior[hp.ang2pix(new_nside, t, p, nest=nest)] += post
#		return new_posterior

###
def p_value(posterior, theta, phi, nside=None):
	"""
	computes the p-value at which a given point was found
	"""
	if not nside:
		nside = hp.npix2nside(len(posterior))
	return np.sum(posterior[posterior>=posterior[hp.ang2pix(nside, theta, phi)]])

###
def estang(posterior, nside=None):
	"""
	returns the position associated with the maximum of the posterior
	"""
	if not nside:
		nside = hp.npix2nside(len(posterior))
	return hp.pix2ang(nside, posterior.argmax())

###
def searched_area(posterior, theta, phi, nside=None, nest=False, degrees=False):
	"""
	computes the searched area given a location
	"""
	if not nside:
		nside = hp.npix2nside(len(posterior))
	ipix = hp.ang2pix(nside, theta, phi, nest=nest)
	return sum(posterior>=posterior[ipix])*hp.nside2pixarea(nside, degrees=degrees)

###
def est_cos_dtheta(posterior, theta, phi):
	"""
	returns the angular separation between the maximum of the posterior and theta, phi
	"""
	t, p = estang(posterior)
	return cos_dtheta(theta, phi, t, p)

###
def min_cos_dtheta(posterior, theta, phi, nside=None, nest=False):
	"""
	computes the maximum angular separation between any point in the area with p > p(theta, phi) and the estimated position
	"""
	if not nside:
		nside = hp.npix2nside(len(posterior))
	ipix = hp.ang2pix(nside, theta, phi, nest=nest)
	## get all ang included in this area
	thetas, phis = hp.pix2ang(nside, np.arange(len(posterior))[posterior >= posterior[ipix]])

	t, p = estang(posterior)

	return np.min(cos_dtheta(thetas, phis, t, p))

###
def num_modes(posterior, theta, phi, nside=None, nest=False):
	"""
	computes the number of modes in the area bounded by theta, phi
	"""
	npix = len(posterior)
	if not nside:
		nside = hp.npix2nside(npix)
	pix = list(np.arange(npix)[posterior>=posterior[hp.ang2pix(nside, theta, phi, nest=nest)]]) ## get list of pixels
	return len( __into_modes(nside, pix) )

### 
def size_modes(posterior, theta, phi, nside=None, nest=False, degrees=False):
	"""
	computes the sizes of modes in the area bounded by theta, phi
	"""
	npix = len(posterior)
	if not nside:
		nside = hp.npix2nside(npix)
	pix = list(np.arange(npix)[posterior>=posterior[hp.ang2pix(nside, theta, phi, nest=nest)]])
	return [len(_)*hp.nside2pixarea(nside, degrees=degrees) for _ in __into_modes(nside, pix)]

###
def __into_modes(nside, pix):
	"""
	divides the list of pixels (pix) into simply connected modes
	"""
	modes = []
	while len(pix):
		mode = []
		to_check = [pix.pop(0)] # take the first pixel
		while len(to_check): # there are pixels in this mode we have to check
			ipix = to_check.pop() # take one pixel from those to be checked.
			for neighbour in hp.get_all_neighbours(nside, ipix):# get neighbors as rtheta, rphi
				# try to find pixel in skymap
				try:
					_ipix = pix.pop( pix.index( neighbour ) ) ### find pixel in skymap and remove it
					mode.append( _ipix ) # add pixel to this mode
					to_check.append( _ipix ) # add pixel to to_check
				except ValueError: # neighbour not in list
					pass
		modes.append( mode )
	return modes

###
def entropy(posterior, base=2.0):
	"""
	computes the shannon entropy in the posterior
	we compute the entropy with base=base
		base=2 => bits
		base=e => nats
	"""
	posterior = posterior[posterior > 0.0] ### log(0)*0 -> 0
	return -np.sum( np.log(posterior)*posterior)/np.log(base)

###
def information(posterior, base=2.0):
	"""
	computes the shannon entropy in the posterior
	we compute the entropy with base=base
		base=2 => bits
		base=e => nats
	"""
	n = len(posterior)
	posterior = posterior[posterior > 0.0] ### log(0)*0 -> 0
	logbase = np.log(base)
	return (np.log(n) + np.sum( np.log(posterior)*posterior) )/np.log(base)

#=================================================
#
# methods for comparing two skymaps
#
#=================================================
def mse(posterior1, posterior2):
	"""
	computes the mean square error between the two posteriors
		sum (p1 - p2)**2
	"""
	return 1.0*np.sum( (posterior1-posterior2)**2 )/len(posterior1)

###
def fidelity(posterior1, posterior2):
	"""
	computes the fidelity between the two posteriors
		sum (p1*p2)**0.5
	"""
	return np.sum( (posterior1*posterior2)**0.5 )

###
def KLdivergence(posterior1, posterior2, base=2.0):
	"""
	computes the Kullback-Leibler divergence
		sum log(p1/p2) * p1
	"""
	truth = posterior1>0
	return np.sum( np.log(posterior1[truth]/posterior2[truth])*posterior1[truth] )/np.log(base)

###
def symmetric_KLdivergence(posterior1, posterior2, base=2.0):
	"""
	computes the symmetric Kullback-Leibler divergence
		sum log(p1/p2)*(p1 - p2)
	"""
	return KLdivergence(posterior1, posterior2, base=base) + KLdivergence(posterior2, posterior2, base=base)
#	return np.sum( np.log(posterior1/posterior2)*(posterior1 - posterior2) )/np.log(base)

###
def structural_similarity(posterior1, posterior2, c1=(0.01)**2, c2=(0.03)**2):
	"""
	computes the structural similarity
		(2*m1*m2+c1)*(2*v12 + c2) / (m1**2 + m2**2 + c1)*(v1 + v2 + c2)
	dynamic range of our pixels is 1
	m1 => mean(p1)
	v1 => var(p1)
	v12=> covar(p1,p2)
	"""
	m1 = np.mean(posterior1)
	m2 = np.mean(posterior2)
	covar = np.cov(posterior1, posterior2)
	return ( (2*m1*m2+c1)*(2*covar[0,1] + c2) ) / ( (m1**2 + m2**2 + c1)*(covar[0,0] + covar[1,1] + c2) )

### 
def pearson(posterior1, posterior2):
	"""
	computes the pearson correlation coefficient
	"""
	covar = np.cov(posterior1, posterior2)
	return covar[0,1]/(covar[0,0]*covar[1,1])**0.5

###
def dot(posterior1, posterior2):
	"""
	takes the "inner product" of the two posteriors and returns the cos(theta) between them
	"""
	return posterior1*posterior2/(np.sum(posterior1**2)*np.sum(posterior2**2))

###
def geometric_overlap(pix1, pix2, nside, degrees=False):
        """
        computes the amount of area in the intersection and union of confidence regions from p1 and p2 defined by p_value
        """
        npix = hp.nside2npix(nside)
        pixarea = hp.nside2pixarea(nside, degrees=degrees)

	posterior1 = np.zeros((npix,),int)
	posterior2 = np.zeros((npix,),int)

	posterior1[pix1] = 1
	posterior2[pix2] = 1

        intersection = np.sum( posterior1*posterior2 )
        return intersection*pixarea, (np.sum(posterior1+posterior2) - intersection)*pixarea

