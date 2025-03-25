#!/usr/bin/env python

import argparse
import numpy as np
from pylal import SimInspiralUtils
import lal
import lalsimulation as lalsim

parser = argparse.ArgumentParser()
parser.add_argument("--inj", dest="inj", default=None, help="Injection XML Path")
parser.add_argument("--event", dest ="event", type=int, default=None, help="Event Number")
parser.add_argument("--frame", dest ="frame", default="OrbitalL", help="Spin Frame of injection")
args = parser.parse_args()

injname = args.inj
event = args.event
frame = args.frame

def sph2cart(r,theta,phi):
    """
    Utiltiy function to convert r,theta,phi to cartesian co-ordinates.
    """
    x = r*np.sin(theta)*np.cos(phi)
    y = r*np.sin(theta)*np.sin(phi)
    z = r*np.cos(theta)
    return x,y,z

def cart2sph(x,y,z):
    """
    Utility function to convert cartesian coords to r,theta,phi.
    """
    r = np.sqrt(x*x + y*y + z*z)
    theta = np.arccos(z/r)
    phi = np.fmod(2*np.pi + np.arctan2(y,x), 2*np.pi)

    return r,theta,phi

def array_dot(vec1, vec2):
    """
    Calculate dot products between vectors in rows of numpy arrays.
    """
    if vec1.ndim==1:
        product = (vec1*vec2).sum()
    else:
        product = (vec1*vec2).sum(axis=1).reshape(-1,1)
    return product



def array_ang_sep(vec1, vec2):
    """
    Find angles between vectors in rows of numpy arrays.
    """
    vec1_mag = np.sqrt(array_dot(vec1, vec1))
    vec2_mag = np.sqrt(array_dot(vec2, vec2))
    return np.arccos(array_dot(vec1, vec2)/(vec1_mag*vec2_mag))

def array_polar_ang(vec):
    """
    Find polar angles of vectors in rows of a numpy array.
    """
    if vec.ndim==1:
        z = vec[2]
    else:
        z = vec[:,2].reshape(-1,1)
    norm = np.sqrt(array_dot(vec,vec))
    return np.arccos(z/norm)

#}}}

def orbital_momentum(f_ref, mc, inclination, m1,m2,eta):
    #{{{
    Lmag = np.power(mc, 5.0/3.0) / np.power(np.pi * lal.MTSUN_SI * f_ref, 1.0/3.0)
    v0 = ((m1+m2)*lal.MTSUN_SI * np.pi *f_ref)**(1./3.)
    Lmag= Lmag*(1.0 + (v0**2) *  (2.5 -eta/6.) )

    Lx, Ly, Lz = sph2cart(Lmag, inclination, 0.0)
    return np.hstack((Lx,Ly,Lz))

def ROTATEZ(angle, vx, vy, vz):
    # This is the ROTATEZ in LALSimInspiral.c.
    tmp1 = vx*np.cos(angle) - vy*np.sin(angle);
    tmp2 = vx*np.sin(angle) + vy*np.cos(angle);
    return np.asarray([tmp1,tmp2,vz])

def ROTATEY(angle, vx, vy, vz):
    # This is the ROTATEY in LALSimInspiral.c
    tmp1 = vx*np.cos(angle) + vz*np.sin(angle);
    tmp2 = -1.0*vx*np.sin(angle) + vz*np.cos(angle);
    return np.asarray([tmp1,vy,tmp2])

def extract_inj_vals(sim_inspiral_event):
    a1, a2, spin1z, spin2z, theta_jn, phi_jl, tilt1, tilt2, phi12 = calculate_injected_sys_frame_params(sim_inspiral_event)
    injvals={
        'mc'          : sim_inspiral_event.mchirp,
	'q'           : sim_inspiral_event.mass2/sim_inspiral_event.mass1,
	'time'        : float(sim_inspiral_event.get_end()),
	'phi_orb'     : sim_inspiral_event.coa_phase,
        'dist'        : sim_inspiral_event.distance,
        'logdistance' : np.log(sim_inspiral_event.distance),
        'ra'          : sim_inspiral_event.longitude,
	'dec'         : sim_inspiral_event.latitude,
        'sindec'      : np.sin(sim_inspiral_event.latitude),
        'psi'         : np.mod(sim_inspiral_event.polarization, np.pi),
        'a1'          : a1,
        'a2'          : a2,
        'spin1'       : spin1z,
        'spin2'       : spin2z,
        'phi12'       : phi12,
        'tilt1'       : tilt1,
        'tilt2'       : tilt2,
        'costilt1'    : np.cos(tilt1),
        'costilt2'    : np.cos(tilt2),
        'theta_jn'    : theta_jn,
        'costheta_jn' : np.cos(theta_jn),
        'phi12'       : phi12,
        'phi_jl'      : phi_jl}
    return injvals

def calculate_injected_sys_frame_params(sim_inspiral_event, f_ref = 100.0):

    # Extract injection parameters.
    m1 = sim_inspiral_event.mass1
    m2 = sim_inspiral_event.mass2
    m1_MSUN = m1*lal.MSUN_SI
    m2_MSUN = m2*lal.MSUN_SI
    mc = sim_inspiral_event.mchirp
    eta = sim_inspiral_event.eta

    # Calc Lmag
    L = orbital_momentum(f_ref, sim_inspiral_event.mchirp, sim_inspiral_event.inclination,m1,m2,eta)

    # Get axis from frame
    axis = lalsim.SimInspiralGetFrameAxisFromString(frame)

    # Convert to radiation frame
    iota, s1x, s1y, s1z, s2x, s2y, s2z = \
          lalsim.SimInspiralInitialConditionsPrecessingApproxs(sim_inspiral_event.inclination,sim_inspiral_event.spin1x, sim_inspiral_event.spin1y, sim_inspiral_event.spin1z, sim_inspiral_event.spin2x, sim_inspiral_event.spin2y, sim_inspiral_event.spin2z, m1_MSUN, m2_MSUN, f_ref, axis)

    a1, theta1, phi1 = cart2sph(s1x, s1y, s1z)
    a2, theta2, phi2 = cart2sph(s2x, s2y, s2z)

    S1 = np.hstack((s1x, s1y, s1z))
    S2 = np.hstack((s2x, s2y, s2z))

    S1 *= m1**2
    S2 *= m2**2
    J = L + S1 + S2

    J = ROTATEY(-2.0*iota, J[0], J[1], J[2])
    L = ROTATEY(-2.0*iota, L[0], L[1], L[2])
    S1 = ROTATEY(-2.0*iota, S1[0], S1[1], S1[2])
    S2 = ROTATEY(-2.0*iota, S2[0], S2[1], S2[2])

    tilt1 = array_ang_sep(L, S1) if not all([i==0.0 for i in S1]) else 0.0
    tilt2 = array_ang_sep(L, S2) if not all([i==0.0 for i in S2]) else 0.0

    if sim_inspiral_event.spin1x == 0.0 and sim_inspiral_event.spin1y == 0.0:
        spin1z = sim_inspiral_event.spin1z
    else:
        spin1z = a1 * np.cos(tilt1)

    if sim_inspiral_event.spin2x == 0.0 and sim_inspiral_event.spin2y == 0.0:
        spin2z = sim_inspiral_event.spin2z
    else:
        spin2z = a2 * np.cos(tilt2)

    # Need to do rotations of XLALSimInspiralTransformPrecessingInitialConditioin inverse order to go in the L frame
    # first rotation: bring J in the N-x plane, with negative x component
    phi0 = np.arctan2(J[1], J[0])
    phi0 = np.pi - phi0
    J = ROTATEZ(phi0, J[0], J[1], J[2])
    L = ROTATEZ(phi0, L[0], L[1], L[2])
    S1 = ROTATEZ(phi0, S1[0], S1[1], S1[2])
    S2 = ROTATEZ(phi0, S2[0], S2[1], S2[2])
    theta_jn = array_polar_ang(J)

    # now J in in the N-x plane and form an angle theta_jn with N, rotate by -theta_jn around y to have J along z
    J = ROTATEY(theta_jn,J[0],J[1],J[2])
    L = ROTATEY(theta_jn,L[0],L[1],L[2])
    S1 = ROTATEY(theta_jn,S1[0],S1[1],S1[2])
    S2 = ROTATEY(theta_jn,S2[0],S2[1],S2[2])

    # J should now be || z and L should have a azimuthal angle phi_jl
    phi_jl = np.arctan2(L[1], L[0])
    phi_jl = np.pi - phi_jl

    # bring L in the Z-X plane, with negative x
    J = ROTATEZ(phi_jl, J[0], J[1], J[2])
    L = ROTATEZ(phi_jl, L[0], L[1], L[2])
    S1 = ROTATEZ(phi_jl, S1[0], S1[1], S1[2])
    S2 = ROTATEZ(phi_jl, S2[0], S2[1], S2[2])

    theta0 = array_polar_ang(L)
    J = ROTATEY(theta0, J[0], J[1], J[2])
    L = ROTATEY(theta0, L[0], L[1], L[2])
    S1 = ROTATEY(theta0, S1[0], S1[1], S1[2])
    S2 = ROTATEY(theta0, S2[0], S2[1], S2[2])

    # The last rotation is useless as it won't change the differenze in spins' azimuthal angles
    phi1 = np.arctan2(S1[1],S1[0])
    phi2 = np.arctan2(S2[1],S2[0])
    if phi2 < phi1:
        phi12 = phi2 - phi1 + 2.*np.pi
    else:
        phi12 = phi2 - phi1

    return a1, a2, spin1z, spin2z, theta_jn, phi_jl, tilt1, tilt2, phi12

###### DO STUFF

injection_table = SimInspiralUtils.ReadSimInspiralFromFiles([injname])
injection_object = injection_table[event]
injection_values = extract_inj_vals(injection_object)

for parameter in injection_values:
	print('injected %r: %r' % (parameter, injection_values[parameter]))

