import numpy as np;
from scipy.optimize import fsolve;
import matplotlib.pyplot as plt;
import time;
import itertools;

def getTangentsIntersections(circ):
	"""Obtains the tangent lines of all circles that emanate from the origin
	of the first circle (the star whose light is being considered at the moment)
	After that, this function finds the points of intersection between each pair
	of circles, and converts them into angles from the center of the first circle.
	The ranges of these angles are then broken up into a number of parts, prescribed
	by a step number."""

	circles = np.array(circ);
	circles.T[1] -= circles[0][1];
	circles.T[2] -= circles[0][2];
	
	t_circles = circles.T;
	
	tans = np.array([])
	
	tangents = np.zeros(len(circles)) + np.pi;
	tangents_var = np.zeros(len(circles)) + np.pi
	tangents[t_circles[1] != 0.] = np.arctan2(t_circles[2][t_circles[1] != 0.],t_circles[1][t_circles[1] != 0.]);
	tangents_var[t_circles[2]**2 + t_circles[1]**2 != 0] = np.arcsin(t_circles[0][t_circles[2]**2 + t_circles[1]**2 != 0]/np.sqrt(t_circles[2]**2 + t_circles[1]**2)[t_circles[2]**2 + t_circles[1]**2 != 0]);
	
	eps = np.finfo(np.float32).eps
	tans = np.concatenate((tangents - tangents_var + 5 * eps, tangents - tangents_var - 5 * eps, tangents, tangents + tangents_var - 5 * eps, tangents + tangents_var + 5 * eps));
	intersectors = np.array([a for a in itertools.combinations(np.arange(0,len(circ)), 2)]);
	
	intersections = np.zeros(len(intersectors)) + np.pi;
	intersections_var = np.zeros(len(intersectors)) + np.pi;
	
	qa = np.array([circles[a[0]][1] for a in intersectors]);
	qb = np.array([circles[a[1]][1] for a in intersectors]);
	ra = np.array([circles[a[0]][2] for a in intersectors]);
	rb = np.array([circles[a[1]][2] for a in intersectors]);
	
	q = qb - qa;
	r = rb - ra;
	
	d1 = np.array([circles[a[0]][0] for a in intersectors]);
	d2 = np.array([circles[a[1]][0] for a in intersectors]);
	
	
	intersections[r != 0] = np.arctan2(q[r != 0], r[r != 0]);
	intersections_var[r != 0] = np.arccos(((q**2 + r**2 + d1**2 - d2**2)[r != 0])/((2. * np.sqrt(q**2 + r**2) * d1)[r!=0]));
	
	intersect1 = np.arctan2((np.sin(intersections + intersections_var) * d1 + ra), (d1 * np.cos(intersections + intersections_var) + qa));
	intersect2 = np.arctan2((np.sin(intersections - intersections_var) * d1 + ra), (d1 * np.cos(intersections - intersections_var) + qa));
	
	
	ff = np.concatenate((intersect1, intersect2));
	return (circ, np.unique(tans[np.isfinite(tans)]), np.unique(ff[np.isfinite(ff)]));
	
def generateRadiiThetas(n, circles, *args):
	"""Generates many steps of angle in between the tangents and intersections of the first function.
	After that, uses a quadratic equation to get the radius from the center of the first circle
	of many points on the other circles (planets and moons).

	Points at zero and the radius of the outer circle (the maximum bound for our limits of integration)
	are also added, and may be retained or removed in the next function.
	"""
	r = np.unique(np.concatenate(args));
	#r = np.concatenate((r, -r, np.pi/2. - r, np.pi * 3./2. + r));
	r = np.concatenate((r, -r, np.pi + r, np.pi - r));
	r = np.sort(r);
	r[(r < 0.) | (r > 2 * np.pi)] %= 2 * np.pi;
	angles = np.unique(np.concatenate([np.linspace(r[o], r[o + 1], n) for o in range(0,len(r) - 1)]));

	radii = np.zeros((len(circles) * 4, len(angles)));
	
	for c in range(1, len(circles)):
	
		a = 1.;
		b = -2. * (circles[c][1] *np.cos(angles) + circles[c][2] * np.sin(angles))
		ci = circles[c][1]**2 + circles[c][2]**2 - circles[c][0]**2
			
		radius_1 = (-b + np.sqrt(b**2 - 4.*a*ci))/(2. * a);
		radius_2 = (-b - np.sqrt(b**2 - 4.*a*ci))/(2. * a);
		
		radius_1[radius_1 >= circles[0][0]] = circles[0][0];
		radius_1[radius_1 <= -circles[0][0]] = -circles[0][0];
		radius_2[radius_2 >= circles[0][0]] = circles[0][0];
		radius_2[radius_2 <= -circles[0][0]] = -circles[0][0];
		
		
		radii[4 * c - 4][np.where(radius_1 > 0.)] = radius_1[radius_1 > 0.];
		radii[4 * c - 3][np.where(radius_2 > 0.)] = radius_2[radius_2 > 0.];
		
		offset_1 = angles[radius_1 < 0.] + np.pi;
		offset_2 = angles[radius_2 < 0.] + np.pi;
		
		for o in offset_1:
			q = np.where(np.absolute(angles - o) < 0.00005);
			radii[4 * c - 2][q] = -radius_1[radius_1 < 0.];
			
		for p in offset_2:
			q = np.where(np.absolute(angles - p) < 0.00005)
			radii[4 * c - 1][q] = -radius_2[radius_2 < 0.];	
			
	return np.transpose(radii), angles;
	
def rd2(coords, circles,opt = 0):
	"""For each point generated, removes duplicates, but ensures that for every theta there is a point
	at R = 0. Deals with negative radii as well. """

	h = time.time();
	
	ind = np.zeros((len(coords[0]), len(coords[0][0])));
	xs = (coords[0].T * np.cos(coords[1]).T).T;
	ys = (coords[0].T * np.sin(coords[1]).T).T;
		
	indicator = np.zeros((len(coords[0]), len(coords[0][0])));
		
	for m in circles[1:]:
		indicator[(((xs - m[1])**2 + (ys - m[2])**2 < (m[0] * 0.9999)**2) & (coords[0] - circles[0][0] < 0.0001)) & ((xs != 0) | (ys != 0))] += 1;
		indicator[(((xs - m[1])**2 + (ys - m[2])**2 < (m[0] * 0.9999)**2) & (coords[0] - circles[0][0] < 0.0001)) & ((xs == 0) & (ys == 0))] -= 1000;
		indicator[(((xs - m[1])**2 + (ys - m[2])**2 < (m[0] * 0.9999)**2) & (coords[0] >= circles[0][0])) & ((xs != 0) | (ys != 0))] -= 1000;
		indicator[np.logical_not((((xs - m[1])**2 + (ys - m[2])**2 < (m[0] * 0.9999)**2) & (abs(coords[0] - circles[0][0]) > 0.0001))) & ((xs == 0.) & (ys == 0.))] += 1;
		indicator[((xs - m[1])**2 + (ys - m[2])**2 > (m[0] * 1.0001)**2)] += 1./(len(circles) - 1);	   
		
	l = time.time() - h;
	#print l
			
	if opt == 1:
		return l;
	if opt == 0:
		return coords[0][indicator < 1], np.vstack([coords[1]] * len(coords[0][0])).T[indicator < 1];
	if opt == 2:
		coords[0][indicator >= 1] -= 1000;
		oh = coords[0];
		u = [np.concatenate((np.unique(oh[a][oh[a] == 0.]), oh[a][(oh[a] > 0.) & (oh[a] < oh[a].max())], np.unique(oh[a][oh[a] == oh[a].max()]))) for a in range(0,len(coords[1]))];
		
		return u, coords[1];
				
def groupAndIntegrate(bounds, num, star_rad, ld_coeff = [1.],ld_power = [0.]):
	"""For each theta, determines the area covered by obscuring bodies by using
	"polar trapezoids" inset in the circular slices d(theta). Multiplies by
	d(theta)/sin(d(theta)) in order to ensure maximum accuracy and compensate
	for the error caused by the small slivers of the obscured circles that are left
	off of the integration.

	It is possible to use any custom limb-darkening law simply by using the ld_power
	and ld_coeffs parameters. These should be the same length and are in order."""

	ld_coeffs = np.array(ld_coeff);
	ld_power = np.array(ld_power);
	rad = [];
	theta = [];

	for a in range(0,len(np.unique(bounds[1]))):
		q = bounds[0][bounds[1] == np.unique(bounds[1])[a]];
		if (len(np.unique(q)) % 2 == 0 and len(q) > 0):
			rad.append(np.unique(q));
			theta.append(np.unique(bounds[1])[a]);

	theta = np.array(theta);	
	d_theta = np.diff(theta);

	#provably (except in tangent line degenerate case or floating point error) there are always
	#an even number of intersections. These cases can simply be ignored with a large enough step number.
	
	area = 0;
	
	s = np.arange(0,len(ld_coeffs));
	s = s[(ld_coeffs[s] != 0)]
					
	for i in np.arange(0,len(d_theta))[::-1] + 1:
		h = 0;
		if ((d_theta[i - 1] < np.pi / (num - 1.)) and d_theta[i - 1] > 3. * np.finfo(np.float32).eps):
			for m in s:
				n = ld_power[m];
				r = 0;
				
				r += np.sum((star_rad**2 - rad[i][0::2]**2)**(n/2. + 1) - (star_rad**2 - rad[i][1::2]**2)**(n/2. + 1)) / (np.pi * star_rad**(n+2));
				r += np.sum((star_rad**2 - rad[i - 1][0::2]**2)**(n/2. + 1) - (star_rad**2 - rad[i - 1][1::2]**2)**(n/2. + 1)) / (np.pi * star_rad**(n+2));
				h += r * ld_coeffs[m];
		
			h *= d_theta[i-1]**2/np.sin(d_theta[i-1]);
			
		area += h;
	area /= 4. * np.sum(ld_coeffs);		
	
	return area;
	
#The following are just helper functions used to plot each instance of integration, for diagnostic purposes.
def plot_circles(circ):
	for q in circ:
		o = np.linspace(-q[0], q[0], 101);
		p = np.sqrt(q[0]**2 - o**2);
		
		plt.plot(o + q[1], p + q[2]);
		plt.plot(o + q[1], q[2] - p);
		
def plot_tangent_lines(tangents, circ):
	for q in tangents:
		o = np.linspace(0, circ[0][0],201);
		plt.plot(o * np.cos(q) + circ[0][1], o * np.sin(q) + circ[0][2]);

