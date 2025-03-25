#!/usr/bin/env python
#-*- coding: utf-8 -*-
"""
The molecules modules serves as an interface to write water molecule input files using predefined geometries, to be used with the DALTON qm package.
"""

from mpl_toolkits.mplot3d import Axes3D
from matplotlib import pyplot as plt

import numpy as np
import re, os, itertools, warnings, subprocess, shutil, logging
import cPickle as pickle

from template import Template
from copy import deepcopy

import read_dal
import gaussian

import h5py
from loprop import *

a0 = 0.52917721092
elem_array = ['X', 'H', 'He', 'Li', 'Be', 'B', 'C', 'N', 'O', 'F', 'Ne']

charge_dict = {"H": 1.0, "C": 6.0, "N": 7.0, "O": 8.0, "S": 16.0,
        "P" : 15, "X" : 0.0 }
# from TIP3P charge defs.
el_charge_dict = {"H": .417, "O": -0.834 , "X" : 0.417 , 'S': -0.25}
mass_dict = {"H": 1.008,  "C": 12.0, "N": 14.01, "O": 15.999, "S": 32.066,
        "X" : 1.008, 'P' : 30.974 }

def upper_triangular(n, start=0):
    """Recursive generator for triangular looping of Carteesian tensor

Usage, form 2D-matrix from upper-triangular matrix represented by an array::

    ref = np.arange( 6 ) # Non-zero elements in 2-dimensional UT-tensor
    arr = np.zeros( (3, 3) ) # Target 
    for ind, (i, ii) in enumerate( upper_triangular(2) ):
        arr[ i, ii ] = ref[ ind ]
"""
    if n > 2:
        for i in range(start, 3):
            for j in upper_triangular(n-1, start=i):
                yield (i,) + j
    else:
        for i in range(start, 3):
            for j in range(i, 3):
                yield i, j

class Property( dict ):
    """
**An object representing properties as numpy.ndarray types mapped to by python dictionaries.**

**Supports up to quadrupoles, upper triangular polarizability and upper trianguler hyperpolarizability**

.. code:: python
    
    >>> p = Property()
    >>> print p["charge"]
    [0.0]

    >>> print p["dipole"]
    [0.0, 0.0, 0.0]

"""
    def __init__(self):

        self["charge"] = np.zeros( 1 )
        self["dipole"] = np.zeros( 3 )
        self["quadrupole"] = np.zeros( 6 )
        self["alpha"] =  np.zeros( 6 ) 
        self["beta"] =  np.zeros( 10 ) 

    def copy_property(self):
        p = Property()
        p["charge"] =      self["charge"].copy()
        p["dipole"] =      self["dipole"].copy()
        p["quadrupole"] =  self["quadrupole"].copy()
        p["alpha"] =       self["alpha"].copy()
        p["beta"] =        self["beta"].copy()
        return p

    def __add__(self, other):
        tmp = Property()
        for i, prop in enumerate(self):
            tmp[prop] = np.array( self[prop] ) + np.array(other[prop] )
        return tmp
    def __sub__(self, other):
        assert isinstance( other, Property)
        tmp = Property()
        for i, prop in enumerate(self):
            tmp[prop] = np.array( self[prop] ) - np.array(other[prop] )
        return tmp

    def potline(self, max_l =2 , pol= 22, hyper=1, fmt = "%.5f "):
        string = ""
        if 0  <= max_l :
            string += fmt % tuple(self["charge"] )
        if max_l >= 1 :
            string += fmt*3 %( self["dipole"][0], self["dipole"][1], self["dipole"][2] )
        if max_l >= 2 :
            string += fmt*6  %( 
                    self["quadrupole"][0], self["quadrupole"][1], self["quadrupole"][2] ,
                    self["quadrupole"][3], self["quadrupole"][4], self["quadrupole"][5] )
        if pol == 1:
            string += fmt %( 
                    float(self["alpha"][0] + self["alpha"][3] + self["alpha"][5])/3,
                    )
        elif pol %10 == 2 :
            string += fmt * 6 %( 
                    self["alpha"][0], self["alpha"][1], self["alpha"][2] ,
                    self["alpha"][3], self["alpha"][4], self["alpha"][5] )
        if hyper == 1:
            string += fmt*10 %( 
                    self["beta"][0], self["beta"][1], self["beta"][2] ,
                    self["beta"][3], self["beta"][4], self["beta"][5] ,
                    self["beta"][6], self["beta"][7], self["beta"][8] ,
                    self["beta"][9])
        return string


    @staticmethod
    def from_propline( st, maxl = 2, pol = 22, hyper = 2 ):
        """
Given dalton POT, returns class Property that can be attached to Atom.

Convinience function for generating properties for the class Molecule directly by 
invoking dalton on a supercomputer.

    >>> p = Property.from_propline( "1 0.0 0.0 0.0 -0.25", maxl = 0 )
    >>> at.Property = p
        """
        st = map( float, st.split()[4:] )
        p = Property()

        p['charge'][0] = st.pop(0)
        if maxl > 0:
            for i in range(3):
                p['dipole'][i] = st.pop(0)
        if maxl > 1:
            for i in range(6):
                p['quadrupole'][i] = st.pop(0)

        if pol == 1:
            iso = st.pop(0)
            p['alpha'][0] = iso
            p['alpha'][4] = iso
            p['alpha'][6] = iso
        elif pol%10 == 2:
            for i in range(6):
                p['alpha'][i] = st.pop(0)
        if hyper == 2:
            for i in range(10):
                p['beta'][i] = st.pop(0)
        return p

    @staticmethod
    def add_prop_from_template( at, wat_templ ):

        """
Puts properties read from the :ref:`template` module into the :ref:`atom` at.

    
    >>> #Dist = True is the default, properties obtained using LoProp
    >>> temp = template.Template().get( dist = False ) 
    >>> w = Water.get_standard() 
    >>> Property.add_prop_from_template( w.o, temp )
    >>> print w.o.Property["dipole"]
    [0.0, 0.0, 0.78719]

"""
        p = Property()
        for i, keys in enumerate( wat_templ ):
            if keys[0] == ( at.element + str(at.order) ):
                p[keys[1]] = np.array( wat_templ[ keys ] )
        at.Property = p
        at.Molecule.Property = True


    def transform_ut_properties( self, t1, t2, t3):
        """
Rotate all the properties of each atom by 3 euler angles.

    >>> w = Water.get_standard()
    >>> w.rotate( 0, np.pi/2, 0 )  #Rotate counter-clockwise by 90 degrees around y-axis
    >>> temp = template.Template().get() #Default template
    >>> Property.add_prop_from_template( w.o, temp )
    >>> print w.o.Property[ "dipole" ]
    array([ 0.   , -0.   ,  0.298])

#Dipole moment of oxygen atom pointing in positive z-direction

    >>> r1, r2, r3 = w.get_euler()
    >>> w.o.Property.transform_ut_properties( r1, r2, r3 )
    >>> print w.o.Property[ "dipole" ]
    [ -2.98000000e-01   3.64944746e-17   1.82472373e-17]

#Dipole moment of oxygen atom now pointing in negative x-direction

"""


        if self.has_key( "dipole" ):
            self["dipole"] = Rotator.transform_1( self["dipole"] , t1, t2, t3 )
        if self.has_key( "quadrupole" ):
            self["quadrupole"] = self.transform_ut_2( self["quadrupole"], t1, t2, t3 )
        if self.has_key( "alpha" ):
            self["alpha"] = self.transform_ut_2( self["alpha"],t1, t2, t3 )
        if self.has_key( "beta" ):
            self["beta"] = self.transform_ut_3( self["beta"], t1, t2, t3 )

    def transform_ut_2( self, prop, t1, t2 ,t3 ):
        tmp = Rotator.ut_2_square( prop )
        tmp = Rotator.transform_2( tmp , t1 ,t2 ,t3 )
        tmp = Rotator.square_2_ut( tmp )
        return tmp

    def transform_ut_3( self, prop, t1, t2 ,t3 ):
        tmp = Rotator.ut_3_square( prop )
        tmp = Rotator.transform_3( tmp, t1 ,t2 ,t3 )
        tmp = Rotator.square_3_ut( tmp )
        return  tmp 


class Generator( dict ):
    """
    Used to create molecules, write dalton .mol files 
    using -param for study with use_calculator.py

    water currently implemented only

    plans to implement methanol

    """
    def __init__(self, *args, **kwargs):

#This waater is TIP3P model,
        self[ ("water", "tip3p", "a_hoh", "degree") ] = 104.52
        self[ ("water", "tip3p", "r_oh", "AA") ] = 0.9572

#This waater is SPC model,
        self[ ("water", "spc", "a_hoh", "degree") ] = 109.47
        self[ ("water", "spc", "r_oh", "AA") ] = 1.0

        self[ ("methanol", "gas_opt", "r_oh", "AA" ) ] = 0.967
        self[ ("methanol", "gas_opt", "r_co", "AA" ) ] = 1.428
        self[ ("methanol", "gas_opt", "r_ch", "AA" ) ] = 1.098

        self[ ("methanol", "gas_opt", "a_coh", "degree" ) ] = 107.16
        self[ ("methanol", "gas_opt", "a_hch", "degree" ) ] = 109.6
        self[ ("methanol", "gas_opt", "a_hco", "degree" ) ] = 109.342

        self[ ("methanol", "gas_opt", "d_hcoh", "h4", "degree" ) ] =  60.0
        self[ ("methanol", "gas_opt", "d_hcoh", "h5", "degree" ) ] = -60.0
        self[ ("methanol", "gas_opt", "d_hcoh", "h6", "degree" ) ] =  180.0

        
#Default options for water
        for val in ["r", "tau", "theta", "rho1", "rho2", "rho3", ]:
            self[ ( val, 'min') ]    = 0.0
            self[ ( val, 'max') ]    = 0.0
            self[ ( val, 'points') ] = 1
        self[ ( 'r', 'min') ]    = 5.0
        self[ ( 'r', 'max') ]    = 10.0
        self[ ( 'r', 'points') ] = 1

# Set by default all parameters to False
        for val in ["r", "tau", "theta", "rho1", "rho2", "rho3", ]:
            self[ ( val, "active" ) ]  = False

    @staticmethod
    def get_b3lypqua_dal( ):
        return """**DALTON INPUT
.RUN RESPONSE
.DIRECT
.PARALLELL
**WAVE FUNCTION
.DFT
B3LYP
.INTERFACE
**INTEGRAL
.DIPLEN
.SECMOM
**RESPONSE
.PROPAV
XDIPLEN
.PROPAV
YDIPLEN
.PROPAV
ZDIPLEN
*QUADRATIC
.QLOP
.DIPLEN
**END OF DALTON INPUT""" 

    @staticmethod
    def get_hfqua_dal( ):
        return """**DALTON INPUT
.RUN RESPONSE
.DIRECT
.PARALLELL
**WAVE FUNCTION
.HF
.INTERFACE
**INTEGRAL
.DIPLEN
.SECMOM
**RESPONSE
.PROPAV
XDIPLEN
.PROPAV
YDIPLEN
.PROPAV
ZDIPLEN
*QUADRATIC
.QLOP
.DIPLEN
**END OF DALTON INPUT""" 

    def gen_mols_param(self, mol = "water", 
            model = 'tip3p',
            basis = ["ano-1 2 1", "ano-1 3 2 1"],
            AA = True,
            worst = False):
        r = np.linspace( self[ ('r', 'min')] , self[ ('r', 'max')] ,
            self[ ('r', 'points' ) ]  )
        tau = np.linspace( self[ ('tau', 'min')] , self[ ('tau', 'max')] ,
            self[ ('tau', 'points' ) ] )
        theta = np.linspace( self[ ('theta', 'min')] , self[ ('theta', 'max')] ,
            self[ ('theta', 'points' )  ] )
        rho1 = np.linspace( self[ ('rho1', 'min')], self[ ('rho1', 'max')],
            self[ ('rho1', 'points' )  ] )
        rho2 = np.linspace( self[ ('rho2', 'min')], self[ ('rho2', 'max')],
            self[ ('rho2', 'points' )  ] )
        rho3 = np.linspace( self[ ('rho3', 'min')], self[ ('rho3', 'max')],
            self[ ('rho3', 'points' )  ] )

        
        if model == 'tip3p':
            r_oh = self[ ("water", 'tip3p', "r_oh", "AA") ]
            a_hoh = np.pi * self[ ("water", 'tip3p', "a_hoh", "degree" )] / 180.0
        else:
            r_oh = self[ ("water", 'tip3p', "r_oh", "AA") ]
            a_hoh = np.pi * self[ ("water", 'tip3p', "a_hoh", "degree" )] / 180.0

        for i in r:
            for j in tau:
                for k in theta:
                    for l in rho1:
                        for m in rho2:
                            for n in rho3:
                                c= Cluster()
                                w1 = self.get_mol( [0, 0, 0], 
                                        mol = mol,
                                        model = model, AA = AA)
                                if worst:
                                    w1 = self.get_mol( [0, 0, 0], 
                                            mol = mol,
                                            model = model, AA = AA)
                                    w1.populate_bonds()
                                    w1.populate_angles()
                                    w1.h1.scale_angle( 0.988 )
                                    w1.h1.scale_bond( 0.985 )
                                    w1.h2.scale_bond( 1.015 )
                                    w1.inv_rotate()

                                c.add_mol( w1, in_qm = True )
                                x, y, z = self.polar_to_cartesian( i, j, k )
                                w2 = self.get_mol( [x,y,z], mol, AA = AA)
                                w2.rotate( l, m, n )

                                c.add_mol( w2, in_qm = True )
                                name = ""
                                name += "-".join( map( str, ["%3.2f"%i, "%3.2f"%j, "%3.2f"%k, "%3.2f"%l, "%3.2f"%m, "%3.2f"%n] ) )
                                name += ".mol"

                                tmp_mol = c.get_qm_mol_string( AA = AA,
                                        basis = tuple(basis),
                                        )
                                f_ = open(name, 'w')
                                f_.write( tmp_mol )
        return 0

    def vary_parameters( self, opts ):
        """Given two parameters, e.g. r and theta, keeps all other static
        param_list should be list of strings of parameters
        ["r":{"min": 2, "max":5, "points": 10}, "rho1" , ... ]

        Has sane defaults, but can be overrided by passing arguments to 
        main program as:

        -r_min 5
        -r_max 10
        -r_points 10

        Which overrides defaults 

        """
        for val in opts:
            self[ (val, 'active') ] = True
            self[ (val, 'min') ] = opts[val][ "min" ]
            self[ (val, 'max') ] = opts[val][ "max" ]
            self[ (val, 'points') ] = opts[val][ "points" ]

    def get_mol( self, 
            center = [0,0,0], 
            mol = "water", 
            model = "tip3p",
            AA = False ):
        """return molecule in center, all molecules have different definition
        of euler angles

        for water place O in origo
        for methanol place C=O bond in origo
        
        """

        if mol == "water":
#Geometrical parameters, dependent om model
            if model == "tip3p":
                r_oh = self[ ("water", "tip3p", "r_oh", "AA") ]
                a_hoh = self[ ("water", "tip3p", "a_hoh","degree") ]

            if model == "spc":
                r_oh = self[ ("water", "spc", "r_oh", "AA") ]
                a_hoh = self[ ("water", "spc", "a_hoh","degree") ]

            if not AA:
                r_oh = r_oh / a0

            d = (90 - a_hoh/2 ) * np.pi / 180


            xo = center[0]
            yo = center[1]
            zo = center[2] 

            xh1 = (center[0] + r_oh * np.cos(d))
            yh1 =  center[1] 
            zh1 = (center[2] + r_oh* np.sin(d))

            xh2 = (center[0] - r_oh * np.cos(d)) 
            yh2 = center[1] 
            zh2 = (center[2] + r_oh* np.sin(d))

            h1 = Atom( **{ "AA" : AA,
                "x" : xh1,
                "y" : yh1,
                "z" : zh1,
                "element" : "H"} )
            h2 = Atom( **{ "AA" : AA,
                "x" : xh2,
                "y" : yh2,
                "z" : zh2,
                "element" : "H"} )
            o = Atom( **{ "AA" : AA,
                "x" : xo,
                "y" : yo,
                "z" : zo,
                "element" : "O"} )

            w = Water( AA = AA)
            w.append( o )
            w.append( h1 )
            w.append( h2 )
            
            return w

        elif mol == "methanol":

            r_co = self[ ("methanol", "gas_opt", "r_co", "AA" )]
            r_oh = self[ ("methanol", "gas_opt", "r_oh", "AA" )]
            r_ch = self[ ("methanol", "gas_opt", "r_ch", "AA" )]

            a_coh = self[ ("methanol", "gas_opt", "a_coh", "degree" ) ]
            #a_hch = self[ ("methanol","gas_opt",  "a_hch", "degree" ) ]
            a_hco = self[ ("methanol", "gas_opt", "a_hco", "degree" ) ]

            a_coh *= np.pi / 180
            a_hco *= np.pi / 180

            d_hcoh_4 = self[ ("methanol","gas_opt",  "d_hcoh", "h4", "degree" ) ]
            d_hcoh_4 *= np.pi / 180
            d_hcoh_5 = self[ ("methanol","gas_opt",  "d_hcoh", "h5", "degree" ) ]
            d_hcoh_5 *= np.pi / 180
            d_hcoh_6 = self[ ("methanol","gas_opt",  "d_hcoh", "h6", "degree" ) ]
            d_hcoh_6 *= np.pi / 180

            if not AA:
                r_co, r_oh, r_ch = r_co/a0, r_oh/a0, r_ch/a0

            c1 = Atom( **{"x":0, "y":0, "z":-r_co/2, "AA": AA, "element":"C" } )
            o2 = Atom( **{"x":0, "y":0, "z": r_co/2, "AA": AA, "element":"O" } )

            h3 = Atom( **{"x":r_oh*np.cos( a_coh-np.pi/2),
                "y":0,
                "z":r_oh*np.sin( a_coh-np.pi/2) + r_co/2,
                "AA": AA, "element":"H" } )

            h4 = Atom( **{"x": r_ch*np.sin( a_hco ) * np.cos( d_hcoh_4 ),
                "y": r_ch*np.sin( a_hco) * np.sin( d_hcoh_4 ),
                "z": r_ch*np.cos( a_hco) - r_co/2 ,
                "AA": AA, "element":"H" } )
            h5 = Atom( **{"x": r_ch*np.sin( a_hco ) * np.cos( d_hcoh_5 ),
                "y": r_ch*np.sin( a_hco) * np.sin( d_hcoh_5 ),
                "z": r_ch*np.cos( a_hco) - r_co/2 ,
                "AA": AA, "element":"H" } )
            h6 = Atom( **{"x": r_ch*np.sin( a_hco ) * np.cos( d_hcoh_6 ),
                "y": r_ch*np.sin( a_hco) * np.sin( d_hcoh_6 ),
                "z": r_ch*np.cos( a_hco) - r_co/2 ,
                "AA": AA, "element":"H" } )

            m = Methanol()
            m.append(c1)
            m.append(o2)
            m.append(h3)
            m.append(h4)
            m.append(h5)
            m.append(h6)

            return m

    def polar_to_cartesian(self, r, tau, theta):
        x, y, z = r* np.sin( theta )*np.cos( tau ) \
               , r* np.sin(  theta )*np.sin( tau )  \
               , r* np.cos(  theta ) 

        return x , y , z

    def one_mol_gen(self, mol = 'water', model = 'tip3p',):
        """
        Only implemented for water so far"""


        if mol == "water":
            d = self[ ("r_oh_dev", "max") ]
            p = self[ ("r_oh_dev", "points") ]
            r_d =  0.01*np.linspace( -d, d, p )

            d = self[ ("theta_hoh_dev", "max") ]
            p = self[ ("theta_hoh_dev", "points") ]
            theta_d =  0.01*np.linspace( -d, d, p )

            #a_hoh = self[ ( mol, model, "a_hoh", "degree" ) ] *np.pi/180
            #r_oh = self[ ( mol, model, "r_oh", "AA" ) ]

            for i in r_d:
                for j in r_d:
                    for k in theta_d:
                        scale_bond1 = 1 + i
                        scale_bond2 = 1 + j
                        scale_angle = 1 + k
                        names = map( lambda x:"%.3f"%x, [i, j, k] )
                        w = self.get_mol( mol = mol, model = model)
                        w.populate_bonds() ; w.populate_angles()
                        w.h1.scale_bond( scale_bond1 )
                        w.h2.scale_bond( scale_bond2 )
                        w.h1.scale_angle( scale_angle )
                        w.inv_rotate()
                        open( "_".join([model]+names) + ".mol",'w').write(w.get_mol_string())
        
    def build_pna( self,  xyz = "tmp.xyz", waters = 0,
            min_r = 2.0,
            mult_r = 10,
            seed = 111 ):
        pna = Molecule.from_xyz( xyz )
        freqs = [ "0.0", "0.0238927", "0.0428227", "0.0773571" ] 

        np.random.seed( seed )

        c = Cluster()
        c.add_mol(pna, in_qm = True)
        cnt = 0
        while cnt < waters:
# Random rotation angles
            t1 = np.random.uniform( 0, np.pi/2 )
            t2 = np.random.uniform( 0, np.pi   )
            t3 = np.random.uniform( 0, np.pi/2 )

# random length, rho and tau 
            r =  np.random.uniform( min_r , min_r * mult_r)
            tau =  np.random.uniform( 0, np.pi*2)
            theta =  np.random.uniform( 0,np.pi)

            center = self.polar_to_cartesian( r, tau, theta )

            wat = self.get_mol( center = pna.com + center,
                    mol = "water")

            wat.rotate( t1, t2, t3 )
            wat.res_id = cnt

            if c.mol_too_close( wat ):
                continue

#We are satisfied with this position, add properties to the water, and rotate them according to t1, t2, t3 so they match the water orientation
            c.add_mol( wat, in_mm = True )
            cnt += 1

        for f_mm in freqs:
            for dist in ["nodist", "dist"]:
                for wat in [ m for m in c if m.in_mm ]:
                    t1, t2, t3 =  wat.get_euler()
                    kwargs_dict = Template().get( *("TIP3P", "HF", "ANOPVDZ",
                        dist == "dist",f_mm ) )
                    for at in wat:
                        Property.add_prop_from_template( at, kwargs_dict )
                    Property.transform_ut_properties( wat.h1.Property, t1,t2,t3 )
                    Property.transform_ut_properties( wat.h2.Property, t1,t2,t3 )
                    Property.transform_ut_properties( wat.o.Property,  t1,t2,t3 )
#Write out QM and MM region separately with properties
                open("pna.mol" ,'w').write(c.get_qm_mol_string(
                    basis= ("ano-1 2 1", "ano-1 3 2 1"),
                    AA = True))
                open("%dmm_%s_%s.pot" %(waters, f_mm, dist ),'w').write(c.get_qmmm_pot_string( in_AA = True ))
                open("tmp.xyz", 'w').write( c.get_xyz_string() )



class Rotator(object):
    """
**Container class for rotational operations on points, vectors, and tensors.**
"""

    def __init__(self):
        pass

    class RotatorError( Exception ):
        def __init__(self):
            pass

    @staticmethod
    def b_hrs( b):
        if b.shape == (10,):
            b = Rotator.ut_3_square(b)
        elif b.shape != (3,3,3,):
            print "supplied wrong beta"
            raise RotatorError

        zzz = Rotator.rot_avg( b )
        xzz = Rotator.rot_avg( b, car1=0 )
        return np.sqrt( zzz + xzz )

    @staticmethod
    def dr( b ):
        if b.shape == (10,):
            b = Rotator.ut_3_square(b)
        elif b.shape != (3,3,3,):
            print "supplied wrong beta"
            raise SystemExit

        zzz = Rotator.rot_avg( b )
        xzz = Rotator.rot_avg( b, car1=0 )
        return zzz / xzz

    @staticmethod
    def rot_avg( beta, car1 = 2, car2 = 2, car3 = 2):
        """
        Requires euler.h5 binary file containing rotational angle products
        Define it as in current script directory + euler.h5
        """
        b_new = np.zeros( (3,3,3,) )
        """given beta in molecular frame, convert to exp. reference"""
        vec = h5py.File( os.path.join(os.path.dirname( os.path.realpath( __file__ )), 'euler.h5' ), 'r')['data'].value
        for X in range(3):
            if X != car1:
                continue
            for Y in range(3):
                if Y != car2:
                    continue
                for Z in range(3):
                    if Z != car3:
                        continue
                    for x1 in range(3):
                        for y1 in range(3):
                            for z1 in range(3):
                                for x2 in range(3):
                                    for y2 in range(3):
                                        for z2 in range(3):
                                            b_new[X,Y,Z] += vec[X,Y,Z,x1,y1,z1,x2,y2,z2] * beta[x1,y1,z1] * beta[x2,y2,z2]
        return b_new[ car1, car2, car3 ]

    @staticmethod
    def transform_1( qm_dipole, t1, t2, t3 ):
        """
Rotate vector around z-axis clockwise by :math:`\\rho_{1}`, around the y-axis counter-clockwise by :math:`\\rho_2`, and finally clockwise around the z-axis by :math:`\\rho_3`.

.. code:: python

    >>> import numpy as np
    >>> d = np.array( [ 1, 0, 0] )
    >>> print Rotator.transform_1( d, 0, numpy.pi/2, 0 )
    [ 0.0, 0.0, 1.0 ]
"""
        d_new1 = np.zeros([3]) #will be returned
        d_new2 = np.zeros([3]) #will be returned
        d_new3 = np.zeros([3]) #will be returned

        rz  = Rotator.get_Rz( t1 )
        ryi = Rotator.get_Ry_inv( t2 )
        rz2 = Rotator.get_Rz( t3 )

        for i in range(3):
            for x in range(3):
                d_new1[i] += rz[i][x] * qm_dipole[x]
        for i in range(3):
            for x in range(3):
                d_new2[i] += ryi[i][x] * d_new1[x]
        for i in range(3):
            for x in range(3):
                d_new3[i] += rz2[i][x] * d_new2[x]
        return d_new3
    @staticmethod
    def transform_2( qm_alpha, t1, t2 , t3 ):
        a_new1 = np.zeros([3,3]) #will be calculated
        a_new2 = np.zeros([3,3]) #will be calculated
        a_new3 = np.zeros([3,3]) #will be calculated

        rz  = Rotator.get_Rz( t1 )
        ryi = Rotator.get_Ry_inv( t2 )
        rz2 = Rotator.get_Rz( t3 )

        for i in range(3):
            for j in range(3):
                for x in range(3):
                    for y in range(3):
                        a_new1[i][j] += rz[i][x] * rz[j][y] * qm_alpha[x][y]

        for i in range(3):
            for j in range(3):
                for x in range(3):
                    for y in range(3):
                        a_new2[i][j] += ryi[i][x] * ryi[j][y] * a_new1[x][y]

        for i in range(3):
            for j in range(3):
                for x in range(3):
                    for y in range(3):
                        a_new3[i][j] += rz2[i][x] * rz2[j][y] * a_new2[x][y]

        return a_new3

    @staticmethod
    def inv_3( beta, t1, t2, t3):
        """Will inversely rotate tensor """
        assert beta.shape == (3,3,3)
        r1 = Rotator.get_Rz_inv( t1 )
        r2 = Rotator.get_Ry( t2 )
        r3 = Rotator.get_Rz_inv( t3 )
        return reduce(lambda a,x: np.einsum('ia,jb,kc,abc', x, x, x, a), [r1,r2,r3], beta )

    @staticmethod
    def transform_3( qm_beta, t1, t2, t3 ):
        b_new1 = np.zeros([3,3,3]) #will be calculated
        b_new2 = np.zeros([3,3,3]) #will be calculated
        b_new3 = np.zeros([3,3,3]) #will be calculated

        rz =  Rotator.get_Rz( t1 )
        ryi = Rotator.get_Ry_inv( t2 )
        rz2 = Rotator.get_Rz( t3 )

        for i in range(3):
            for j in range(3):
                for k in range(3):
                    for x in range(3):
                        for y in range(3):
                            for z in range(3):
                                b_new1[i][j][k] += rz[i][x] * rz[j][y] * rz[k][z] * qm_beta[x][y][z]
        for i in range(3):
            for j in range(3):
                for k in range(3):
                    for x in range(3):
                        for y in range(3):
                            for z in range(3):
                                b_new2[i][j][k] += ryi[i][x] * ryi[j][y] * ryi[k][z] * b_new1[x][y][z]
        for i in range(3):
            for j in range(3):
                for k in range(3):
                    for x in range(3):
                        for y in range(3):
                            for z in range(3):
                                b_new3[i][j][k] += rz2[i][x] * rz2[j][y] * rz2[k][z] * b_new2[x][y][z]
        return b_new3

    @staticmethod
    def square_2_ut(alpha):
        assert alpha.ndim == 2
        tmp_a = np.zeros( 6 )
        for index, (i, j ) in enumerate( upper_triangular(2) ):
            tmp_a[ index ] = (alpha[i, j] + alpha[ j, i]) / 2
        return tmp_a

    @staticmethod
    def get_Rz( theta ):
        vec = np.array(    [[ np.cos(theta),-np.sin(theta), 0],
                            [ np.sin(theta), np.cos(theta), 0],
                            [ 0,    0,  1]])
        return vec
    @staticmethod
    def get_Rz_inv( theta ):
        vec = np.array(     [[ np.cos(theta), np.sin(theta), 0],
                            [ -np.sin(theta), np.cos(theta), 0],
                            [ 0,             0,            1]])
        return vec
    @staticmethod
    def get_Ry( theta ):
        vec = np.array(    [[ np.cos(theta),0, np.sin(theta)],
                            [ 0,    1,  0],
                            [ -np.sin(theta), 0, np.cos(theta)]])
        return vec
    @staticmethod
    def get_Ry_inv( theta ):
        vec = np.array(    [[ np.cos(theta),0, -np.sin(theta)],
                            [ 0,    1,  0],
                            [ np.sin(theta), 0, np.cos(theta)]])
        return vec

    @staticmethod
    def tensor_to_ut( beta ):
# naive solution, transforms matrix B[ (x,y,z) ][ (xx, xy, xz, yy, yz, zz) ] into array
# Symmtrized UT array    B[ (xxx, xxy, xxz, xyy, xyz, xzz, yyy, yyz, yzz, zzz) ]
        new = np.zeros( (10) )
        new[ 0 ] = beta[0,0]
        new[ 1 ] = (beta[0,1] + beta[1,0] ) /2
        new[ 2 ] = (beta[0,2] + beta[2,0] ) /2
        new[ 3 ] = (beta[0,3] + beta[1,1] ) /2
        new[ 4 ] = (beta[0,4] + beta[1,2] + beta[2,1] ) /3
        new[ 5 ] = (beta[0,5] + beta[2,2] ) /2
        new[ 6 ] = beta[1,3]
        new[ 7 ] = (beta[1,4] + beta[2,3] ) /2
        new[ 8 ] = (beta[1,5] + beta[2,4] ) /2
        new[ 9 ] = beta[2,5]
        return new
    @staticmethod
    def square_3_ut(beta):
        assert beta.ndim == 3
        tmp_b = np.zeros( 10 )
        for index, (i, j, k ) in enumerate( upper_triangular(3) ):
            tmp_b[ index ] = ( \
                    beta[i, j, k] + beta[i, k, j] + \
                    beta[j, i, k] + beta[j, k, i] + \
                    beta[k, i, j] + beta[k, j, i] )/ 6
        return tmp_b

    @staticmethod
    def ut_2_square( alpha):
        assert len(alpha) == 6
        tmp_a = np.zeros( (3,3, ))
        for index, val in enumerate( upper_triangular(2) ) :
            tmp_a[ val[0], val[1] ] = alpha[ index ]
            tmp_a[ val[1], val[0] ] = alpha[ index ]
        return tmp_a

    @staticmethod
    def ut_3_square( beta ):
        assert len(beta) == 10
        tmp_b = np.zeros( (3,3,3, ))
        for index, (i, j, k ) in enumerate( upper_triangular(3) ) :
            tmp_b[ i, j ,k] = beta[ index ]
            tmp_b[ i, k ,j] = beta[ index] 
            tmp_b[ j, i, k] = beta [ index ]
            tmp_b[ j, k, i] = beta [ index ]
            tmp_b[ k, i, j] = beta [ index ]
            tmp_b[ k, j, i] = beta [ index ]
        return tmp_b


class Atom(object):

    """
    **Object representation of atoms.**
    """
    def __init__(self, *args, **kwargs ):
        """
Initialize either directly:

.. code:: python

    >>> a = Atom( x = 0, y = 0, z = 0, 'element' = 'H', AA = True )

... or with pre-defined key-word arguments:

.. code:: python

    >>> kwargs = { 'x' : 0, 'y' : 0, 'z' : 0, 'element' : 'H', "AA" : True }
    >>> a = Atom( **kwargs )

List of key-word arguments:

======== ======== ========
Keyword  Default  Type
======== ======== ========
x        0.0      float
y        0.0      float
z        0.0      float
element  X        string
name     1-XXX-X1 string
pdb_name  X1       string
number   0        int
AA       True     bool
======== ======== ========

        """
#Element one-key char
        self.element = "X"

#Order in xyz files
        self.order = None

#Name is custom name, for water use O1, H2 (positive x ax), H3
        self.name = None
#Label is custom name, for water use O1, H2 (positive x ax), H3
        self.label = ""

        self.x = 0.0
        self.y = 0.0
        self.z = 0.0


# Use populate_bonds in class Molecule to attach all atoms to their neighbours
        self.bonds = {}
        self.angles = {}
        self.dihedral = {}

        self._q = None

        self.cluster = None

        self.number = 0
        self._res_id = 0
        self.atom_id = None

        self.in_water = False
        self.Molecule = Molecule()

        self.in_qm = False
        self.in_mm = False
        self.in_qmmm = False
#Property set to true if atoms have properties
        self.Property = Property()
        self.AA = True

        if kwargs != {}:
            self.AA = bool( kwargs.get( "AA", False ) )
            self.x = float( kwargs.get( "x", 0.0 ))
            self.y = float( kwargs.get( "y", 0.0 ))
            self.z = float( kwargs.get( "z", 0.0 ))
            self.element = kwargs.get( "element", "X" )
            self.name = kwargs.get( "name", "1-XXX-X1" )
            self.number = kwargs.get( "number", 0 )
            self.pdb_name = kwargs.get( "pdb_name", 'X1' )
            self.order = kwargs.get( "order", 0 )
            self.in_qm = kwargs.get( "in_qm", False )
            self.in_mm = kwargs.get( "in_mm", False )
            self.in_qmmm = kwargs.get( "in_qmmm", False )
            self._res_id = kwargs.get( "res_id", 0 )
        self._mass = None


    def plot(self ):
        """
Plot Atom in a 3D frame

.. code:: python

    >>> a = Atom( element = 'H' )
    >>> a.plot()
    
"""

#Plot water molecule in green and  nice xyz axis
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d' )
        ax.plot( [0, 1, 0, 0, 0, 0], [0,0 ,0,1,0,0], [0,0,0,0,0,1] )
        ax.text( 1.1, 0, 0, "X", color = 'red' )
        ax.text( 0, 1.1, 0, "Y", color = 'red' )
        ax.text( 0, 0, 1.1, "Z", color = 'red' )

        ax.plot( [self.x], [self.y], [self.z], self.Molecule.style[self.element], linewidth= self.Molecule.linewidth[self.element] )
        ax.set_zlim3d( -5,5)
        plt.xlim(-5,5)
        plt.ylim(-5,5)
        plt.show()



    def __len__( self ):
        return 1
    def __iter__(self):
        yield self
    def __getitem__(self, ind):
        if ind ==0 :
            return self.x
        elif ind ==1 :
            return self.y
        elif ind ==2 :
            return self.z

    def scale_angle(self, scale = 1.0):
        """scales only angle
        
        defaults to 1.0"""

        if len(self.angles) > 1:
            warnings.warn("Did not scale %s since it had %d angles" %(self,len(self.angles)), Warning)
            return
        Rz, Rzi = Rotator.get_Rz, Rotator.get_Rz_inv
        Ry, Ryi = Rotator.get_Ry, Rotator.get_Ry_inv

        for at2, at3 in self.angles:
            r3 = self.bonds[at2].bonds[at3].r - self.bonds[at2].r 
            t = self.bonds[at2].r.copy()
            for i in self.Molecule:
                i.x, i.y, i.z = i.r - t

            rho1 = np.math.atan2( r3[1], r3[0] )
            for i in self.Molecule:
                r3 = np.dot( Rzi(rho1), r3 )
                i.x, i.y, i.z = np.dot( Rzi(rho1), i.r )

            rho2 = np.math.atan2( -r3[0], r3[2] )
            for i in self.Molecule:
                r3 = np.dot( Ry(rho2), r3 )
                i.x, i.y, i.z = np.dot( Ry(rho2), i.r )

            rho3 = np.math.atan2( r3[1], r3[0] )
            for i in self.Molecule:
                i.x, i.y, i.z = np.dot( Rzi(rho3), i.r )
            theta = scale*self.get_angle( self.bonds[at2], self.angles[(at2,at3)] )

            bond = self.get_bond( self.bonds[at2] )
            self.x = bond * np.sin(theta)
            np.testing.assert_almost_equal( self.y, 0 )
            self.z = bond* np.cos( theta)

            for i in self.Molecule:
                i.x, i.y, i.z = np.dot( Rz(rho3), i.r )
                i.x, i.y, i.z = np.dot( Ryi(rho2), i.r )
                i.x, i.y, i.z = np.dot( Rz(rho1), i.r )
                i.x, i.y, i.z = i.r + t

    def get_bond(self, other):
        return np.linalg.norm(other.r - self.r)

    def get_angle(self, at1, at2 ):
        r1 = self.r - at1.r
        r2 = at2.r - at1.r
        n1 = np.linalg.norm(r1)
        n2 = np.linalg.norm(r2)
        deg = np.arccos(np.dot(r1,r2)/(n1*n2)) 
        return deg

    def scale_bond(self, scale = 1.0):
        """scales only bond by a scalefactor 
        
        scale defaults to 1.0"""

        if len(self.bonds) > 1:
            warnings.warn("Did not scale %s since it had %d bonds" %(self,len(self.bonds)), Warning)
            return
        for at in self.bonds:
            self.translate( self.bonds[at].r + (self.r - self.bonds[at].r)*scale )

    def copy(self):
        return self.copy_atom()
    def copy_self(self):
        return self.copy_atom()
    def copy_atom(self):
        a = Atom( **{'x':self.x, 'y':self.y, 'z':self.z,'AA':self.AA,
            'element':self.element,'name':self.name,'number':self.number,
            'pdb_name':self.pdb_name} )
        a._res_id = self.res_id
        a.atom_id = self.atom_id
        a.Property = self.Property.copy_property()
        return a

    @property
    def r(self):
        return np.array( [ self.x, self.y, self.z ] )

    @property
    def q(self):
        if self.Property:
            return self.Property["charge"]
        if self._q is not None:
            return self._q
        self._q = el_charge_dict[ self.element ]
        return self._q

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        self._mass = mass_dict[ self.element ]
        return self._mass

    @property
    def res_id(self):
        if self.Molecule:
            return self.Molecule.res_id
        return self._res_id

    def potline(self, max_l=2, pol=22, hyper=1):
        return  "{0:4} {1:10f} {2:10f} {3:10f} ".format( \
                str(self.res_id), self.x, self.y, self.z ) + self.Property.potline( max_l, pol, hyper ) + "\n"

    def __str__(self):
        return "%s %f %f %f" %(self.name, self.x, self.y, self.z)

    def __sub__(self, other ):
        return self.r - other.r
    def __add__(self, other ):
        return self.r + other.r

    def get_array(self):
        return np.array( self.r ).copy()

    def dist_to_atom(self, other):

        """
Return the distance between two atoms

.. code:: python

   >>> H1 = Atom( z = 0 )
   >>> H2 = Atom( z = 1 )
   >>> print H1.dist_to_atom( H2 )
   1.0

"""
        return np.sqrt( (self.x - other.x)**2 + (self.y -other.y)**2 + (self.z -other.z)**2 )



    def dist_to_point(self, other):
        """
Return the distance to a point

.. code:: python

   >>> a = Atom( z = 0 )
   >>> print H1.dist_to_point( [0, 3, 4] )
   5.0

"""
        return np.sqrt( (self.x - other[0])**2 + (self.y -other[1])**2 + (self.z -other[2])**2 )

    def to_AU(self):
        if self.AA:
            self.x /= a0
            self.y /= a0
            self.z /= a0
            self.AA = False

    def to_AA(self):
        if not self.AA:
            self.x *= a0
            self.y *= a0
            self.z *= a0
            self.AA = True

class Molecule( list ):
    """
**Inherits list methods, specific molecules will inherit from this class.**
"""

    def __init__(self , *args, **kwargs):
#Bond dict defined in angstromg, if molecule is in AU will be different later
        self.bonding_cutoff = { ('H','H') : 0.8,
                ('H','C') : 1.101,
                ('H','N') : 1.1,
                ('H','O') : 1.1,
                ('H','P') : 1.1,
                ('H','S') : 1.3,
                ('C','C') : 1.66,
                ('C','N') : 1.60,
                ('C','O') : 1.5,
                ('C','P') : 2.0,
                ('C','S') : 2.0,
                ('N','N') : 1.5,
                ('N','O') : 1.5,
                ('N','P') : 1.5,
                ('N','S') : 1.5,
                ('O','O') : 1.5,
                ('O','P') : 2.0,
                ('O','S') : 1.6,
                ('P','P') : 1.5,
                ('P','S') : 2.0,
                ('S','S') : 2.1,
            }
        for key1, key2 in self.bonding_cutoff.keys():
            self.bonding_cutoff[ (key2, key1)] = self.bonding_cutoff[ (key1, key2) ]

# Dictionary with bonds
        self.bond_dict = {}

#center will be defined for all molecules after all atoms are added
#depends on which molecule
        self.res_id = 0
        self._r = None
        self._com = None
        self.cluster = None
        self.no_hydrogens = True

# This will be set True if attaching LoProp properties
        self.LoProp = False

# For plotting different elements:
        self.style = { "X": 'ko' ,"H":'wo', "N":'bo',"C":'go',"P":'ko', "O":'ro',
                'S' : 'yo'}
        self.linewidth = {"X":25,"H":25, "N": 30, "C": 30, "O":40, "P" : 40,
                'S' : 45 }

# Make emptpy, beware that this causes molecules to give zero dipole momnet
# before template is loaded
        self.Property = None

#By default, AU 
        self.AA = False

#if supplied a dictionary with options, gather these in self.info
        self.info = {}
        if kwargs != {} :
            for i in kwargs:
                self.info[ i ] = kwargs[ i ]
            self.AA = kwargs.get( "AA" , False )
 
    def save(self, fname = "molecule.p"):
        pickle.dump( self, open( fname, 'wb' ), protocol = 2 )

    @staticmethod
    def load(fname = 'molecule.p'):
        if not os.path.isfile( fname):
            raise IOError
        return pickle.load( open(fname, 'rb' ) )
    
    @property
    def b_proj(self):
        b, p = Rotator.ut_3_square(self.sum_property['beta']), self.sum_property['dipole']
        return np.einsum( 'ijj,i', b, p )/np.linalg.norm( p )

    def attach_properties(self, 
            model = "TIP3P",
            method = "HF",
            basis = "ANOPVDZ",
            loprop = True,
            freq = "0.0"):
        """
Attach property for Molecule method, by default TIP3P/HF/ANOPVDZ, static
        """
        templ = Template().get( *(model, method, basis, loprop, freq) )
        for at in self:
            Property.add_prop_from_template( at, templ )
        t1, t2, t3 = self.get_euler()
        for at in self:
            at.Property.transform_ut_properties( t1, t2, t3 )
        if loprop:
            self.LoProp = True
        else:
            self.LoProp = False
        self.Property = True

    def dist_to_point( self , point ):
        return np.sqrt(np.sum((self.com - np.array(point))**2))

    def get_euler(self):
        """Will be overwritten by specific molecule classes"""
        return np.zeros(3)

    def rotate(self, t1, t2, t3):
        """Molecular Rotation function

        Will rotate around center-of-mass by default

        If we have properties, transform them as well
        """
# Place water molecule in origo, and rotate it so hydrogens in xz plane
        #self.inv_rotate()

        com = self.com.copy()
        orig = np.zeros( (len(self), 3) )
# Rotate with angles t1, t2, t3
        for at in self:
            at.x, at.y, at.z = np.dot( Rotator.get_Rz(t1), at.r )
            at.x, at.y, at.z = np.dot( Rotator.get_Ry_inv(t2), at.r )
            at.x, at.y, at.z = np.dot( Rotator.get_Rz(t3), at.r )

        if self.Property:
            for at in self:
                at.Property.transform_ut_properties( t1, t2, t3 )

#Put back in original point
        for ind, at in enumerate(self):
            at.x += com[0]
            at.y += com[0]
            at.z += com[0]

    def props_from_qm(self,
            tmpdir = '/tmp',
            dalpath = None,
            procs = 4,
            decimal = 5,
            maxl = 1,
            pol = 22,
            hyper = 2,
            method = 'hf',
            env = os.environ,
            basis = ['ano-1 2', 'ano-1 4 3 1', 'ano-1 5 4 1' ],
            dalexe = None,
            basdir = '/home/x_ignha/repos/dalton/basis',
            ):
        """
        Will generate a .mol file of itself, run a DALTON calculation as a
        childed process, get the properties back and put them on all atoms.

        Might take long time for large residues.
        """

#Specific for triolith host, will remove in slurm environment leftover RSP
#files if they exist in tmp dir
        if os.environ.has_key( 'SLURM_JOB_NAME' ):
#Set allocated temporary directory
            tmpdir = os.environ['SNIC_TMP']
            for f_ in [f for f in os.listdir(tmpdir) if "RSP" in f]:
                if os.path.isfile( os.path.join( tmpdir, f_ ) ):
                    os.remove( os.path.join( tmpdir, f_) )
        else:
            tmpdir = os.path.join( tmpdir, str(os.getpid()) )
            if not os.path.isdir( tmpdir ):
                os.mkdir( tmpdir )

        dal = 'dalton.dal'
        mol = 'molecule.mol'
        dal_full, mol_full = map( lambda x: os.path.join( tmpdir, x ), [dal,mol])
        if method == 'hf':
            open( dal, 'w').write( Generator.get_hfqua_dal( ) )
        elif method == 'b3lyp':
            open( dal, 'w').write( Generator.get_b3lypqua_dal( ) )
        else:
            print "wrong calculation type specified"
            return
        open( mol, 'w').write( self.get_mol_string( basis = basis) )

#Make sure that the external dalton script copies the .out and .tar.gz
#files from calculation to current directory once child process finishes

        if dalexe is not None:
#On triolith modern dalton can only be run this custom way
            p = subprocess.Popen(['sbcast', dal,
                os.path.join( tmpdir , 'DALTON.INP')],
                stdout = subprocess.PIPE )
            out, err = p.communicate()
            p = subprocess.Popen(['sbcast', mol,
                os.path.join( tmpdir, 'MOLECULE.INP'), ],
                stdout = subprocess.PIPE )
            out, err = p.communicate()
        elif os.path.isfile( dalpath ):
            dalton = dalpath
        elif env.has_key( 'DALTON' ):
            dalton = env['DALTON']
        else:
            print "set env variable DALTON to dalton script, \
             or supply the script to props_from_qm directly as  \
             dalpath = <path-to-dalscript> "
            raise SystemExit


        if dalexe:
#Run as dalton executable directly in the dir with *.INP files
            os.chdir( tmpdir )
            p = subprocess.Popen([ 
                "WORK_MEM_MB=1024",
                "WRKMEM=$(($WORK_MEM_MB*131072))"
                "DALTON_TMPDIR=%s"%tmpdir,
                "BASDIR=%s" %basdir,
                "mpprun",
                "-np",
                "%d" %procs,
                dalexe], stdout = subprocess.PIPE )
            out, err = p.communicate()

            tar = "final.tar.gz"
            of = "DALTON.OUT"
            p = subprocess.Popen(['tar',
                'cvfz',
                'AOONEINT','AOPROPER','DALTON.BAS',
                'SIRIFC','RSPVEC','SIRIUS.RST',
                tar
                ],
                stdout = subprocess.PIPE)
        else:
#Run as dalton script
            p = subprocess.Popen([dalton, 
                '-N', str(procs), '-noarch', '-D', '-noappend', '-t', tmpdir,
                dal, mol
                ], stdout = subprocess.PIPE,
                )
            out, err = p.communicate()
            of = "DALTON.OUT"
            tar = "dalton_molecule.tar.gz"
            of, tar = map( lambda x: os.path.join( tmpdir, x ), [of, tar ] )
        at, p, a, b = read_dal.read_beta_hf( of )

#Using Olavs external scripts
        try:
            outpot = MolFrag( tmpdir = tmpdir,
                    max_l = maxl,
                    pol = pol,
                    pf = penalty_function( 2.0 ),
                    freqs = None,
                    ).output_potential_file(
                            maxl = maxl,
                            pol = pol,
                            hyper = hyper,
                            decimal = decimal,
                            #template_full = False,
                            #decimal = 5,
                            )
        except:
            print tmpdir

        lines = [ " ".join(l.split()) for l in outpot.split('\n') if len(l.split()) > 4 ]
        if not len(lines) == len(self):
            print "Something went wrong in MolFrag output, check length of molecule and the molfile it produces"
            raise SystemExit
        for at, prop in zip(self, lines):
            at.Property = Property.from_propline( prop ,
                    maxl = maxl,
                    pol = pol,
                    hyper = hyper )
        self.LoProp = True


#So that we do not pollute current directory with dalton outputs
#Also remove confliction inter-dalton calculation files
# For triolith specific calculations, remove all files in tmp
        if os.environ.has_key( 'SLURM_JOB_NAME' ):
            try:
                for f_ in [f for f in os.listdir(tmpdir) if os.path.isfile(f) ]:
                    os.remove( f_ )
                for f_ in [mol, dal]:
                    os.remove( f_ )
            except OSError:
                pass
        else:
            try:
                os.remove( tar )
            except OSError:
                pass
            os.remove( of )
            shutil.rmtree( tmpdir )
            for f_ in [mol, dal]:
                try:
                    os.remove( f_ )
                except OSError:
                    pass

    @classmethod
    def from_string(cls, fil):
        """Given .xyz file return a Molecule with these atoms"""
        rel = open(fil).readlines()[2:]
        m = cls()
        for i in range(len(rel)):
            m.append( Atom(**{'element':rel[i].split()[0],
                'x':rel[i].split()[1],
                'y':rel[i].split()[2],
                'z':rel[i].split()[3].strip(),
                'number' : i+1,
                }) )
        return m

    def custom_names(self):
        for i in self:
            i.name = i.element + str(i.number)

    def populate_bonds(self):
#Implement later that it can only be called once
        bond_dict = {}
        for i, at in enumerate( self ):
            bond_dict[ at ] = []

        if self.AA:
            conv = 1.0
        else:
            conv = 1/a0
        for i in range(len(self)):
            for j in range( i + 1, len(self) ):
                if self[i].dist_to_atom( self[j] ) < conv*self.bonding_cutoff[ (self[i].element, self[j].element) ]:

                    self[i].bonds[ self[j].name ] = self[j]
                    self[j].bonds[ self[i].name ] = self[i]
                    bond_dict[ self[i] ].append( self[j] )
                    bond_dict[ self[j] ].append( self[i] )
        self.bond_dict = bond_dict

    def populate_angles(self):
# Must be run after populate_bonds
        for at1 in self:
            for at2 in [at2 for at2 in at1.bonds.values()]:
                for at3 in [at3 for at3 in at2.bonds.values() if at3 is not at1 ]:
                    at1.angles[(at2.name,at3.name)] = at3

    @staticmethod
    def from_charmm_file( f):
        """Return molecule just by bonds from a charmm force field file
        
        Good for generation of dihedrals
        """
        m = Molecule()
        reg_at = re.compile(r'ATOM\s\w+\s+\w+\s+-*\d{1}.\d+\s')
        reg_bond = re.compile(r'BOND\s+')
        reg_el = re.compile(r'(^\w).*')

        ats = []
        for i in open(f).readlines():
            if reg_at.match( i ):
                m.append( Atom( **{ 'name':i.split()[1], 'element': reg_el.match(i.split()[1]).group(1) } ))

        for i in open(f).readlines():
            if reg_bond.match( i ):
                el1 = reg_el.match( i.split()[1]).group(1)
                el2 = reg_el.match( i.split()[2]).group(1)

                m.bond_dict[ (i.split()[1], i.split()[2] ) ] = m.bonding_cutoff[ \
                        (el1, el2) ]
                m.bond_dict[ (i.split()[2], i.split()[1] ) ] = m.bonding_cutoff[ \
                        (el2, el1) ]


        for i in range(len(m)):
            for j in range(len(m)):
                if m.bond_dict.has_key( (m[i].name, m[j].name) ) or \
                    m.bond_dict.has_key( (m[j].name, m[i].name) ) :
                    m[i].bonds.append( m[j] )
                    m[j].bonds.append( m[i] )

        dih = m.find_dihedrals()

        full_charm = ""
        skip = []

        aname_to_atype, atype_to_aname, atype_to_anumber, atype_dihed, anumber_to_atype = m.atom_map_from_string(f)

        for at in m:
            at.number = atype_to_anumber[ at.name ]


        for at in m:
            for targ in at.dihedral:
                l1 =  tuple( at.dihedral[targ] ) 
                l2 =  tuple( reversed(at.dihedral[targ] ) )
                t1 =  tuple( map( lambda x: aname_to_atype[x], at.dihedral[targ] ) )
                t2 =  tuple( reversed(map( lambda x: aname_to_atype[x], at.dihedral[targ] ) ))
                if t1 in atype_dihed:
                    if (l1 in skip) or (l2 in skip):
                        continue
                    skip.append( l1 )
                    pre_str = "\t".join( map( lambda x: str(atype_to_anumber[x]),
                        at.dihedral[targ] ))
                    full_charm += pre_str + "\t" + atype_dihed[ t1 ] + '\n'
                    continue
                if t2 in atype_dihed:
                    if (l2 in skip) or (l2 in skip):
                        continue
                    skip.append( l2 )
                    pre_str = "\t".join( map( lambda x: str(atype_to_anumber[x]),
                        at.dihedral[targ] ))
                    full_charm += pre_str + "\t" + atype_dihed[ t2 ] + '\n'
        return full_charm

    def find_dihedrals(self):

        dihed = []
        for at1 in self:
            if at1.bonds == []:
                continue
            for at2 in at1.bonds:
                if at2.bonds == []:
                    continue
                for at3 in [a for a in at2.bonds if a != at1]:
                    if at3.bonds == []:
                        continue
                    for at4 in [a for a in at3.bonds if a != at2]:
                        dihed.append( [at1.name, at2.name, at3.name, at4.name] )
                        at1.dihedral[ (at3.name, at4.name) ] = (at1.name,at2.name, at3.name, at4.name)
        return dihed

#Dipole moment
    @property
    def p(self):
        """
Return the dipole moment

.. code:: python

   >>> m = Molecule()
   >>> m.append( Atom(element = 'H', z = 1) )
   >>> m.append( Atom(element = 'O', z = 0) )
   >>> print m.p
   -0.834

"""
        el_dip = np.array([ (at.r-self.coc)*at.Property['charge'] for mol in self for at in mol])
        nuc_dip = np.array([ (at.r-self.coc)*charge_dict[at.element] for mol in self for at in mol])
        dip_lop = np.array([at.Property['dipole'] for mol in self for at in mol])
        dip = el_dip + nuc_dip
        return (dip + dip_lop) .sum(axis=0)

    @property
    def sum_property(self):
        """
Return the sum properties of all properties in molecules

.. code:: python
    >>> wat
        """
        el_dip = np.array([ (at.r-self.coc)*at.Property['charge'] for mol in self for at in mol])
        nuc_dip = np.array([ (at.r-self.coc)*charge_dict[at.element] for mol in self for at in mol])
        dip_lop = np.array([at.Property['dipole'] for mol in self for at in mol])
        dip = el_dip + nuc_dip
        d = (dip + dip_lop).sum(axis=0)
        p = Property()
        for at in self:
            p += at.Property
        p['dipole'] = d
        return p

#Vector pointing to center of atom position
    @property
    def r(self):
        """
Center of coordinate

.. code:: python

   >>> m = Molecule()
   >>> m.append( Atom(element = 'H', z = 1) )
   >>> m.append( Atom(element = 'O', z = 0) )
   >>> print m.r
   0.5

"""
        return  np.array([at.r for at in self]).sum(axis = 0) / len(self)

    def translate(self, r):
        """
Translate molecules center-of-mass to position r

.. code:: python

    >>> m = Molecule()
    >>> m.append( Atom(element = 'H', z = 1) )
    >>> m.append( Atom(element = 'H', z = 0) )
    >>> print m.com
    [0, 0, 0.5 ]
    >>> m.translate( [0, 3, 5] )
    >>> print m.com
    [0, 3, 5 ]
    
"""
        vec = r - self.com
        for at in self:
            at.x = vec[0] + at.x 
            at.y = vec[1] + at.y 
            at.z = vec[2] + at.z 
        return self


    def translate_coc(self, r):
        vec = r - self.coc
        for at in self:
            at.x = vec[0] + at.x 
            at.y = vec[1] + at.y 
            at.z = vec[2] + at.z 
        return self

    @staticmethod
    def atom_map_from_string( fil ):
        aname_to_atype = {}
        atype_to_aname = {}
        aname_to_anumber = {}
        atype_dihedral_dict = {}
        anumber_to_atype = {}

        reg = re.compile(r'ATOM\s\w+\s+\w+\s+-*\d{1}.\d+\s')

        reg_dihed = re.compile (r'\w+\s+\w+\s+\w+\s+\w+\s+-*\d.\d+\s+\d{1}')

        cnt = 1
        for i in open(fil).readlines():
            if reg.match(i):
                aname_to_atype[ i.split()[1] ] = i.split()[2]
                atype_to_aname[ i.split()[2] ] = i.split()[1]
                aname_to_anumber[ i.split()[1] ] = cnt
                anumber_to_atype[ cnt ] = i.split()[1]
                cnt += 1
            if reg_dihed.match( i ):
                atype_dihedral_dict[(i.split()[0], i.split()[1],
                    i.split()[2], i.split()[3])] = " ".join( i.split()[4:] )
        return aname_to_atype, atype_to_aname, aname_to_anumber, atype_dihedral_dict, anumber_to_atype


#Center of nuclei charge
    @property
    def coc(self):
        """
Return center of charge

.. code:: python

    >>> m = Molecule()
    >>> m.add_atom( Atom( z : 0.11, element : 'H' ) )
    >>> m.coc
    [0., 0., 0.11]

        """

        if self.Property:
            pass
        return sum( [at.r * charge_dict[at.element] for at in self])\
                /sum( map(float,[charge_dict[at.element] for at in self]) )

    @property
    def com(self):
        return np.array([at.mass*at.r for at in self]).sum(axis=0) / np.array([at.mass for at in self]).sum()

    def dist_to_mol(self, other):
        """
Distance to other molecule, measured by center-of-mass

.. code:: python

    >>> m1 = Molecule( )
    >>> m2 = Molecule( )
    >>> m1.append( Atom()) ; m1.append( Atom( z = 1) )
    >>> m2.append( Atom(x = 1)) ; m2.append( Atom( x = 1, z = 1) )
    >>> print m1.dist_to_mol( m2 )
    1.0
    
"""
        return np.sqrt( ((self.com - other.com)**2 ).sum(axis=0) )


    def plot(self, copy = True, center = False, d = False ):
        """
Plot Molecule in a 3D frame

.. code:: python

    >>> m = Molecule()
    >>> m.append( Atom(element = 'H', x = 1, z = 1) )
    >>> m.append( Atom(element = 'H', x =-1, z = 1) )
    >>> m.append( Atom(element = 'O', z = 0) )
    >>> m.plot()
    
"""

#Make a copy in order to not change original, and perform plot on it
        if copy:
            copy = deepcopy( self )
        else:
            copy = self

        if center:
            copy.center()

#Plot water molecule in green and  nice xyz axis
        copy.populate_bonds()
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d' )
#Plot bonds
        for each in copy.bond_dict:
            for key in copy.bond_dict[ each ]:
                ax.plot( [key.x, each.x],
                         [key.y, each.y],
                         [key.z, each.z], color = 'black' )

        ax.plot( [0, 1, 0, 0, 0, 0], [0,0 ,0,1,0,0], [0,0,0,0,0,1] )
        ax.text( 1.1, 0, 0, "X", color = 'red' )
        ax.text( 0, 1.1, 0, "Y", color = 'red' )
        ax.text( 0, 0, 1.1, "Z", color = 'red' )
        if d:
            x = copy.coc[0]
            y = copy.coc[1]
            z = copy.coc[2]
            p = copy.p
            ax.plot( [x,x+p[0]], [y,y+p[1]], [z,z+p[2]], 'k-', linewidth = 3 )
            ax.plot( [p[0]],[p[1]],[p[2]],'ko', markersize = 5, linewidth = 5 )
        for i in copy:
            ax.plot( [i.x], [i.y], [i.z], copy.style[i.element], linewidth= copy.linewidth[i.element] )

        ax.set_zlim3d( -5,5)
        plt.xlim(-5,5)
        plt.ylim(-5,5)
        plt.show()

    def get_mol_string(self, basis = ("ano-1 2", "ano-1 4 3 1",
        "ano-2 5 4 1" ) ):
        if len( basis ) > 1:
            el_to_rowind = {"H" : 0, "C" : 1, "O" : 1, "N" : 1,
                    "S" : 2, "P" : 2}
        else:
            el_to_rowind = {"H" : 0, "C" : 0, "O" : 0, "N" : 0, "S" : 0 }
        st = ""
        s_ = ""
        if self.AA: s_ += " Angstrom"
        uni = Molecule.unique([ at.element for at in self])
        st += "ATOMBASIS\n\n\nAtomtypes=%d Charge=0 Nosymm%s\n" %(len(uni), s_)
        for el in uni:
            st += "Charge=%s Atoms=%d Basis=%s\n" %( str(charge_dict[el]),
                    len( [all_el for all_el in self if (all_el.element == el)] ),
                    basis[ el_to_rowind[el] ])
            for i in [all_el for all_el in self if (all_el.element == el) ]:
                st += "%s %.5f %.5f %.5f\n" %(i.element, i.x, i.y, i.z ) 
        return st

    @property
    def q(self):
        q = 0
        for at in self:
            q += at.Property['charge']
        return q[0]

    def get_inp_string(self, method ='B3LYP', basis = "6-31+g*", procs= 8):
        """Write gaussian .inp file for geometry optimization"""
        st = r"%" + "Nprocshared=%d\n" %procs
        st += r"%" + "Mem=20MW\n"
        st += "#p %s/%s opt " %(method,basis)
        if not self.AA:
            st += "units=au " 
        st += '\n\ncomment\n\n'
        st += "%d %d\n" %( self.q, 1 )
        for i in self:
            st += "%s %.5f %.5f %.5f\n" %(i.element, i.x, i.y, i.z ) 
        st+= '\n\n\n'
        return st



    @staticmethod
    def unique(arr):
        tmp = []
        for i in arr:
            if i not in tmp:
                tmp.append(i)
        return tmp

    def center(self):

        """
Center molecule with center-of-mass in origo

.. code:: python

    >>> m.com
    [0., 0., 1.,]

    >>> m.center()
    >>> m.com
    [0., 0., 0.,]

"""
        tmp = np.array( [0,0,0] )
        self.translate( tmp )

    @staticmethod
    def from_mol_file( molfile, in_AA = False, out_AA = False):
        """
Read in molecule given .mol file and unit specification.

.. code:: python

    >>> m = ( "water.mol", AA = True )
    >>> for at in m:
            print at.element
    H
    H
    O
    
"""
        pat_xyz = re.compile(r'^\s*(\S+)\s+(-*\d*\.{1}\d+)\s+(-*\d*\.{1}\d+)\s+(-*\d*\.{1}\d+) *$')
        tmp_molecule = Molecule( AA = in_AA )
        for i in open( molfile ).readlines():
            if pat_xyz.search(i):
                matched = pat_xyz.match(i).groups()
                pd = matched[0].split('-')[-1]
                kwargs = { "AA": in_AA, 
                        "element" : matched[0][0],
                        "name" :  matched[0], "x" : matched[1],
                        "y" : matched[2], "z" : matched[3], 
                        "pdb_name" : pd }
                tmpAtom = Atom( **kwargs )
                tmp_molecule.append( tmpAtom )
        if in_AA:
            if not out_AA:
                tmp_molecule.to_AU()
        return tmp_molecule



    @staticmethod
    def from_xyz( f, in_AA = True, out_AA = True ):
        """
Read in molecule from .xyz file given unit specifications.
Resulting molecule will be in either atomic units [ out_AA = False ], or in 
Angstrom [ out_AA = True ]

.. code:: python

    >>> m = ( "water.mol", in_AA = True, out_AA = False )
    >>> for at in m:
            print at.z
    H
    H
    O
    
"""
        if not os.path.isfile( f ):
            raise IOError

        fil = open(f).readlines()
        m = Molecule( AA = in_AA )
        for ind, i in enumerate( fil ):
            if ind in [0, 1]: 
                continue

            elem = i.split()[0]
            x = i.split()[1]
            y = i.split()[2]
            z = i.split()[3]
            at = Atom( **{"element":elem,
                "x" : x,
                "y" : y,
                "z" : z,
                "AA" : in_AA,
#Order later used to read in templates
                "order" : ind - 1,
                'name' : elem + str(ind-1)
                })
            m.append( at )
            at.Molecule = m

        if in_AA:
            if not out_AA:
                m.to_AU()
        return m

    def to_AU(self):
        if self.AA:
            for at in self:
                at.to_AU()
            self.AA = False

    def to_AA(self):
        if not self.AA:
            for at in self:
                at.to_AA()
            self.AA = True

class Water( Molecule ):
    """
**Derives all general methods from Molecule.**

**Specific for water is the get_euler method, which defines which water orientation is the reference position.**
"""

    def __init__(self , *args, **kwargs):
        super(Water, self).__init__( *args, **kwargs )
        self.atoms = 0

        self.no_hydrogens = True
        self.h1 = False
        self.h2 = False
        self.o  = False

        self.AA = False

        self._coc = None

        self.in_qm = False
        self.in_mm = False
        self.in_qmmm = False

        if kwargs is not {}:
            self.AA = kwargs.get( "AA", False )

    def copy(self):
        return self.copy_water()
    def copy_self(self):
        return self.copy_water()
    def copy_water(self):
        w = Water()
        [w.append(i.copy_atom()) for i in self]
        return w
    @staticmethod
    def get_standard( AA = False,
            model = 'tip3p',
            worst = False):
        """
Return water molecule from specified template with :math:`r=0.9572` Angstrom and 
:math:`\\theta=104.52` degrees.

.. code:: python

    >>> m = Water.get_standard()

"""
#Geometrical parameters
        center = [0, 0, 0]
        model = model.lower()
        if model == 'tip3p':
            r_oh = 0.95720
            a_hoh =  104.52
        elif model == 'spc':
            r_oh = 1.00
            a_hoh =  109.47
        r_oh = r_oh / a0
        d = (90 - a_hoh/2 ) * np.pi / 180
        origin = np.array( [ 0, 0, 0] )

        h1 = Atom( **{ "AA" : AA, "element" : "H"} )
        h2 = Atom( **{ "AA" : AA, "element" : "H"} )
        o =  Atom( **{ "AA" : AA, "element" : "O"} )

        o.x = center[0]
        o.y = center[1]
        o.z = center[2] 

        h1.x = (center[0] + r_oh * np.cos(d))
        h1.y = center[1] 
        h1.z = (center[2] + r_oh* np.sin(d))

        h2.x = (center[0] - r_oh * np.cos(d)) 
        h2.y = center[1] 
        h2.z = (center[2] + r_oh* np.sin(d))
        o.order = 1
        h1.order = 2
        h2.order = 3
        w = Water( AA = AA)
        w.append( o )
        w.append( h1 )
        w.append( h2 )
        if worst:
            w.populate_bonds()
            w.populate_angles()
            w.h1.scale_angle( 0.988 )
            w.h1.scale_bond( 0.985 )
            w.h2.scale_bond( 1.015 )
            w.inv_rotate()
        return w

    def is_worst(self):
        self.populate_bonds()
        self.populate_angles()
        r1 = self.h1.dist_to_atom( self.o )
        r2 = self.h2.dist_to_atom( self.o )
        a = self.h1.get_angle( self.o, self.h2 ) /np.pi * 180
        if np.allclose( [r1, r2, a], [1.7817, 1.8360, 103.2658 ] ,atol = 0.0001) or np.allclose( [r2, r1, a], [1.7817, 1.8360, 103.2658 ] ,atol = 0.0001) :
            return True
        return False

    def translate_o(self, r):
        vec = r - self.o.r
        for at in self:
            at.x = vec[0] + at.x 
            at.y = vec[1] + at.y 
            at.z = vec[2] + at.z 
        return self
#Center of oxygen
    @property
    def coo(self):
        return self.o.r
    def append(self, atom):
        """
Override list append method, will add up to 3 atoms,
1 must be oxygen, 2 must be hydrogens.

.. code:: python

    >>> m = Water()
    >>> m.append( Atom( z = 0.11, element = 'H' ) )
    >>> m.coc

"""
        if len(self) > 3:
            print "tried to add additional atoms to water, exiting"
            raise SystemExit

        if not isinstance( atom, Atom ):
            print "wrong class passed to water append"
            raise SystemExit

        if atom.element == "H":
            if self.no_hydrogens:
                self.h1 = atom
                atom.Molecule = self
                self.no_hydrogens = False
            else:
                self.h2 = atom
                atom.Molecule = self
        if atom.element == "O":
            self.o = atom
            atom.Molecule = self
            atom.name = "O1"
#Add the atom
        super( Water , self).append(atom)

#Define water center, by default set it to center of nuclei
        if (self.h1 and self.h2 and self.o):
            pass

        if self.res_id:
            if self.res_id != atom.res_id:
                print "Tried to add %s to %s, exiting" %(atom, self)
                raise SystemExit
        else:
#Initialize water res_id from atomic res_id
            self.res_id = atom.res_id

        if len(self) == 3:
            hyd1, hyd2 = [i for i in self if i.element == "H" ]
            d1 = hyd1.dist_to_point( [1,1,1] )
            d2 = hyd2.dist_to_point( [1,1,1] )
            if d1 < d2:
                self.h1 = hyd1
                self.h2 = hyd2
                hyd1.name = "H2"
                hyd2.name = "H3"
            else:
                self.h1 = hyd2
                self.h2 = hyd1
                hyd1.name = "H2"
                hyd2.name = "H3"

    def __str__(self):
        return "WAT" + str(self.res_id) 
    
    def exclists(self):
        tmp = []
        uniq = []
        for i in itertools.permutations( [at.number for at in self], len(self) ):
            if i[0] not in uniq:
                tmp.append(i)
                uniq.append( i[0] )
        return tmp

    def dist_to_point( self , point ):
        return np.sqrt(np.sum((self.coo - np.array(point))**2))

    def dist_to_water(self, other):
        return np.sqrt(np.sum((self.coo - other.coo)**2) )

    def get_euler(self):
        """
Returns the 3 euler angles required to rotate the water to given coordinate system.
The return values are ordered in :math:`\\rho_1`, :math:`\\rho_2` and :math:`\\rho_3`.

.. code:: python

    >>> w = Water()
    >>> w.append( Atom( x = 1, z = 1, element = 'H' ) )
    >>> w.append( Atom( x =-1, z = 1, element = 'H' ) )
    >>> w.append( Atom( x = 0, z = 1, element = 'O' ) )
    >>> r1, r2, r3 = w.get_euler()
    >>> print r1
    0.0


        """

        H1 = self.h1.r.copy()
        H2 = self.h2.r.copy()
        O1 = self.o.r.copy()

        dip = (-0.5*O1 + 0.25*H1 + 0.25 *H2).copy()

        origin = O1.copy()
        H1, H2, O1 = H1 - origin, H2 - origin, O1 - origin

        theta1 = np.arctan2( dip[1], dip[0])
        if theta1 < 0:
            theta1 += 2 * np.pi

        H1 =  np.dot( Rotator.get_Rz_inv( theta1 ) , H1 )
        H2 =  np.dot( Rotator.get_Rz_inv( theta1 ) , H2 )
        O1 =  np.dot( Rotator.get_Rz_inv( theta1 ) , O1 )

        dip = np.dot( Rotator.get_Rz_inv( theta1 ) , dip )

#Rotate by theta around y axis so that the dipole is in the z axis 
        theta2 = np.arctan2( -dip[0], dip[2] )
        if theta2 < 0:
            theta2 += 2 * np.pi

        H1 =  np.dot( Rotator.get_Ry( theta2 ) , H1 )
        H2 =  np.dot( Rotator.get_Ry( theta2 ) , H2 )
        O1 =  np.dot( Rotator.get_Ry( theta2 ) , O1 )

        dip = np.dot( Rotator.get_Ry( theta2 ) , dip )

#Rotate around Z axis so that hydrogens are in xz plane.
        if H2[1] >0:
            xc = H2[0]
            yc = H2[1]
        else:
            xc = H1[0]
            yc = H1[1]
        theta3 = np.arctan2( yc , xc)
        if theta3 < 0:
            theta3 += 2 * np.pi

        def eq(a, b, thr = 0.0001): 
            if abs(a-b) < thr:return True
            else: return False

        return theta3, theta2, theta1

    def inv_rotate(self):
        """rotate all atom positions by
        1) inverse Z rotation by t1
        2) positive Y rotation by t2
        3) inverse Z rotation by t3

        Inverse rotation around oxygen centre, will conflict with
        self.center() method which centers around center-of-mass.
        """
        t1, t2, t3 = self.get_euler()

        com = self.com.copy()
#Put back in original point
        for at in self:
            at.x, at.y, at.z = at.r - com
        r1 = Rotator.get_Rz_inv(t1)
        r2 = Rotator.get_Ry(t2)
        r3 = Rotator.get_Rz_inv(t3)
        for at in self:
            at.x, at.y, at.z = reduce(lambda a,x:np.einsum('ij,j',x,a),[r1,r2,r3],at.r)
            #at.Property.inv_transform_ut_properties( t1, t2, t3 )
        for at in self:
            at.x, at.y, at.z = at.r + com
        if self.h2.x >= 0:
            tmp = self.h2.r.copy()
            self.h2.x, self.h2.y, self.h2.z = self.h1.r.copy()
            self.h1.x, self.h1.y, self.h1.z = tmp

    def rotate(self, t1, t2, t3):
        """Rotate all coordinates by t1, t2 and t3
        first Rz with theta1, then Ry^-1 by theta2, then Rz with theta 3

        R all in radians

        """
        com = self.com.copy()
        orig = np.zeros( (len(self), 3) )
#Put back in original point
        for at in self:
            at.x, at.y, at.z = at.r - com
        r1 = Rotator.get_Rz(t1)
        r2 = Rotator.get_Ry_inv(t2)
        r3 = Rotator.get_Rz(t3)
        for at in self:
            at.x, at.y, at.z = reduce(lambda a,x:np.einsum('ij,j',x,a),[r1,r2,r3],at.r)
            at.Property.transform_ut_properties( t1, t2, t3 )
        for at in self:
            at.x, at.y, at.z = at.r + com

    def get_xyz_string(self, ):
        st = "%d\n\n" % len(self)
        for i in self:
            st += "{0:10s} {1:10f} {2:10f} {3:10f}\n".format(\
                    i.element, i.x,  i.y , i.z )
        return st

    @staticmethod
    def read_waters( fname , in_AA = True, out_AA = True , N_waters = 1):
        """From file with name fname, return a list of all waters encountered"""
        atoms = []
        if fname.endswith( ".xyz" ) or fname.endswith(".mol"):
            pat_xyz = re.compile(r'^\s*(\w+)\s+(-*\d*.+\d+)\s+(-*\d*.+\d+)\s+(-*\d*.+\d+) *$')
            for i in open( fname ).readlines():
                if pat_xyz.match(i):
                    f = pat_xyz.match(i).groups()
                    matched = pat_xyz.match(i).groups()
                    kwargs = { "element" :  matched[0], "x" : matched[1],
                            "y" : matched[2], "z" : matched[3] }
                    tmpAtom = Atom( **kwargs )
                    atoms.append( tmpAtom )
        elif fname.endswith( ".pdb" ):
            pat1 = re.compile(r'^(ATOM|HETATM)')
            for i in open( fname ).readlines():
                if pat1.search(i):
                    if ( i[11:16].strip() == "SW") or (i[11:16] == "DW"):
                        continue
                    kwargs = {
                            "AA" : in_AA,
                            "x" : float(i[30:38].strip()),
                            "y" : float(i[38:46].strip()),
                            "z" : float(i[46:54].strip()),
                            "element": i[11:16].strip()[0] }
                    tmpAtom = Atom( **kwargs )
                    atoms.append( tmpAtom )
        elif fname.endswith( ".out" ):
            pat_xyz = re.compile(r'^(\w+)\s+(-*\d*.+\d+)\s+(-*\d*.+\d+)\s+(-*\d*.+\d+) *$')
            for i in open( fname ).readlines():
                if pat_xyz.match(i):
                    f = pat_xyz.match(i).groups()
                    tmpAtom = Atom(f[0][0], float(f[1]), float(f[2]), float(f[3]), 0)
                    atoms.append( tmpAtom )
#loop over oxygen and hydrogen and if they are closer than 1 A add them to a water
        waters = []
        cnt = 1
        if fname.endswith( ".xyz" ) or fname.endswith(".mol"):
            for i in atoms:
                if i.element == "H":
                    continue
                if i.in_water:
                    continue
                tmp = Water()
                i.in_water = True
                tmp.append( i )
                for j in atoms:
                    if j.element == "O":
                        continue
                    if j.in_water:
                        continue
#If in angstrom
                    if in_AA:
                        if i.dist_to_atom(j) < 1.1:
                            tmp.append ( j )
                            j.in_water = True
                    else:
                        if i.dist_to_atom(j) < 1.1/a0:
                            tmp.append ( j )
                            j.in_water = True
                tmp.res_id = cnt
                cnt += 1
                waters.append( tmp )
        elif fname.endswith( ".pdb" ):
#Find out the size of the box encompassing all atoms
            xmin = 10000.0; ymin = 10000.0; zmin = 10000.0; 
            xmax = -10000.0; ymax = -10000.0; zmax = -10000.0; 
            for i in atoms:
                if i.x < xmin:
                    xmin = i.x
                if i.y < ymin:
                    ymin = i.y
                if i.z < zmin:
                    zmin = i.z
                if i.x > xmax:
                    xmax = i.x
                if i.y > ymax:
                    ymax = i.y
                if i.z > zmax:
                    zmax = i.z
            center = np.array([ xmax - xmin, ymax -ymin, zmax- zmin]) /2.0
            wlist = []
            for i in atoms:
                if i.element == "H":
                    continue
                if i.in_water:
                    continue
                tmp = Water()
#__Water__.append() method will update the waters residue number and center coordinate
#When all atoms are there
#Right now NOT center-of-mass
                i.in_water= True
                tmp.append(i)
                for j in atoms:
                    if j.element == "O":
                        continue
                    if j.in_water:
                        continue
#1.05 because sometimes spc water lengths can be over 1.01
                    if in_AA:
                        if i.dist_to_atom(j) <= 1.05:
                            j.in_water = True
                            tmp.append( j )
                    else:
                        if i.dist_to_atom(j) <= 1.05/a0:
                            j.in_water = True
                            tmp.append( j )
                tmp.res_id = cnt
                cnt += 1
                wlist.append( tmp )
            wlist.sort( key = lambda x: x.dist_to_point( center ))
            center_water = wlist[0]
            cent_wlist = wlist[1:]
            cent_wlist.sort( key= lambda x: x.dist_to_water( center_water) )

            if N_waters< 1:
                print "Please choose at least one water molecule"
                raise SystemExit
            waters = [center_water] + cent_wlist[ 0 : N_waters - 1 ]

        elif fname.endswith( ".out" ):
            for i in atoms:
                if i.element == "H":
                    continue
                if i.in_water:
                    continue
                tmp = Water()
                i.in_water = True
                tmp.append( i )
                for j in atoms:
                    if j.element == "O":
                        continue
                    if j.in_water:
                        continue
#If in cartesian:
                    if i.AA:
                        if i.dist(j) < 1.0:
                            tmp.append ( j )
                            j.in_water = True
                    else:
                        if i.dist(j) < 1.0/a0:
                            tmp.append ( j )
                            j.in_water = True
                tmp.res_id = cnt
                cnt += 1
                waters.append( tmp )
        for wat in waters:
            for atom in wat:
                atom._res_id = wat.res_id
        if in_AA:
            if not out_AA:
                for wat in waters:
                    wat.to_AU()
        return waters
     
    @staticmethod
    def get_string_from_waters( waters, max_l = 1, pol = 2 , hyper = 0, dist = False, AA = False ):
        """ Converts list of waters into Olav string for hyperpolarizable .pot"""
# If the properties are in distributed form, I. E. starts from Oxygen, then H in +x and H -x

        if AA:
            str_ = "AA"
        else:
            str_ = "AU"
        string = "%s\n%d %d %d %d\n" % ( str_, len(waters)*3,
                max_l, pol, hyper )
        for i in waters:
            for at in i:
                string +=  " ".join([str(at.res_id)] + map(str,at.r)) + " "
                string += at.Property.potline( max_l=max_l, pol=pol, hyper= hyper)
                string += '\n'
        return string




class Methanol(Molecule):
    """
Not yet implemented, only needs get_euler and z-matrix to be specific.
    """

    def __init__(self, *args, **kwargs):
        super( Methanol, self).__init__(**kwargs)

    def append(self, atom):
        """Typical append for each seperate molecule class"""
        if len(self) == 6:
            print "tried to add additional atoms to methanol, exiting"
            raise SystemExit

        if not isinstance( atom, Atom ):
            print "wront class passed to methanol append"
            raise SystemExit

        if atom.element == "H":
            if self.no_hydrogens:
                self.h1 = atom
                self.no_hydrogens = False
            else:
                self.h2 = atom

        if atom.element == "O":
            self.o = atom
#Add the atom
        super( Molecule, self).append(atom)

#Define methanol center, by default set it to center of C=O bond

        if len(self) == 6:
            self.center = sum([ i.r for i in self ] ) / len(self)
            #hc = charge_dict[ self.h1.element ]
            #oc = charge_dict[ self.h1.element ]
            #self.coc = np.array([ self.h1.x * hc  + self.h2.x *hc + self.o.x *oc,  \
            #    self.h1.y *hc + self.h2.y *hc + self.o.y *oc , \
            #    self.h1.z *hc + self.h2.z *hc + self.o.z *oc ]) /( 2*hc +oc)
        if self.res_id:
            if self.res_id != atom.res_id:
                print "Tried to add %s to %s, exiting" %(atom, self)
                raise SystemExit
        else:
#Initialize res_id from atomic res_id
            self.res_id = atom.res_id
#Also calculate center now
        if len(self) == 6:
            h1, h2, h3, h4 = [i for i in self if i.element == "H" ]
            #print "All hyds added for methanol %s" %str(self)
            #raise SystemExit
            #d1 = hyd1.dist_to_point( [1,1,1] )
            #d2 = hyd2.dist_to_point( [1,1,1] )
            #if d1 < d2:
            #    self.h1 = hyd1
            #    self.h2 = hyd2
            #else:
            #    self.h1 = hyd2
            #    self.h2 = hyd1

class Ethane(list):
    def __init__(self):
        pass

class Cluster(list):
    """
**Molecule container which groups molecules into quantum mechanics, molecular mechanics, and qm/mm regions for easy in generating input files for QM/MM.**
"""
    def __init__(self, *args, **kwargs):
        """ Typical list of molecules """
        self.Property = None
        self.atom_list = []
        if type(args) == tuple:
            if len(args) == 1:
                if type(args[0]) == list:
                    for i in args[0]:
                        self.add( i )
                else:
                    self.add( args[0] )
            else:
                for item in args:
                    self.add( item )

    def g_list_from_damped(self, 
            max_l = 1,
            pol = 22,
            hyp = 1,
            rq = 1e-9, rp = 1e-9, AA_cutoff = 1.5,
            nullify = False):
        """Given cutoff in Angstromgs, will return a GassuanQuadrupoleList
        where atomic within AA_cutoff between different interacting segments
        
        has a damped gaussian """

        g = gaussian.GaussianQuadrupoleList.from_string( self.get_qmmm_pot_string() )
        for atom, res in map( lambda x: [x, x.residue], self.min_dist_atoms_seperate_res(AA_cutoff) ):
            ind = reduce( lambda a, x: a + len(x), res.chain[:res.order_nr],0)+atom.order_nr
            g[ ind ]._R_q = rq
            g[ ind ]._R_p = rp
            if nullify:
                g[ ind ]._q = 0.0
                g[ ind ]._p0 = np.zeros( (3,) )
                g[ ind ]._a0 = np.zeros( (3,3,) )
                g[ ind ]._Q0 = np.zeros( (3,3,) )
                g[ ind ]._b0 = np.zeros( (3,3,3,) )
        return g
                    

    @property
    def AA(self):
        AA = [at for res in self for at in res ][0].AA
        for each in [at for res in self for at in res ]:
            try:
                assert each.AA == AA
            except AssertionError:
                logging.error("All objects in cluster are not of same unit")
        return AA

    def __str__(self):
        return " ".join( [ str(i) for i in self ] )
    
    def save(self, fname = "cluster.p"):
        pickle.dump( self, open(fname, 'wb' ), protocol = 2 )

    @staticmethod
    def load(fname = 'cluster.p'):
        if not os.path.isfile( fname):
            raise IOError
        return pickle.load( open(fname, 'rb' ) )
    


    
    @staticmethod
    def get_all_molecules_from_file(fil,
            in_AA = False,
            out_AA = False,
            ):
#dont add atoms to molecule if they are within 1.5 angstrom
        max_dist = 1.5
        if in_AA :
            max_dist / a0

        """Given pdb/mol/xyz  file return a Cluster with all seperate molecules"""
        if fil.endswith('.xyz'):
            with open(fil,'r') as f_:
                pass
    def min_dist_atoms_seperate_res(self, AA_cutoff = 1.5 ):
        """Return list of atoms which have an other atom closer than 1.5 AA to them
        and are not in the same residue
        
        """
        tmp = []
        ats = self.min_dist_atoms( AA_cutoff = AA_cutoff )
        for i in range(len(ats)-1):
            for j in range(  i, len( ats )):
                if ats[i].res_id == ats[j].res_id:
                    continue
                if ats[i].dist_to_atom( ats[j] ) < AA_cutoff:
                    tmp.append( ats[i] )
                    tmp.append( ats[j] )
        return read_dal.unique( tmp )



     
    def min_dist_atoms(self, AA_cutoff = 1.5):
        """Return list of atoms which have an other atom closer than 1.5 AA to them
        
.. code:: python
    
    >>> c = Cluster()
    >>> c.add( Water.get_standard())
    >>> for at in c.min_dist_atoms():
            print at
        O1 0.000000 0.000000 0.000000
        H2 1.430429 0.000000 1.107157
        H3 -1.430429 0.000000 1.107157
        """
        if not self.AA:
            AA_cutoff /= a0
        N_ats = reduce( lambda a,x: a + len(x) , [res for res in self], 0 )
        d_mat = np.full( (N_ats, N_ats ), np.inf )

        ats = [at for res in self for at in res]
        for i1, at1 in enumerate( ats ):
            for i2, at2 in enumerate( ats ):
                if at1 == at2:
                    continue
                d_mat [i1, i2] = at1.dist_to_atom( at2 )
        x, y = np.where( d_mat < AA_cutoff )[0], np.where( d_mat < AA_cutoff) [1]
        min_ats = []

        for xi, zi in zip( x, y ):
            min_ats.append( ats[xi] )
            min_ats.append( ats[zi] )

        return read_dal.unique(min_ats)


    def min_dist_coo(self):
        dist = np.zeros( (len(self),len(self)) )
        new = np.zeros( len(self) - 1 )

        for i in range(len(self)):
            for j in range( i, len(self)):
                if i == j:
                    continue
                dist[i,j] = np.linalg.norm(self[i].coo - self[j].coo)
        for i in range( len(dist) - 1 ):
            c = dist[i,i+1:].copy()
            c.sort()
            new[i] = c[0]
        new.sort()
        return new

    def min_dist_com(self):
        dist = np.zeros( len(self) )
        for i in range(len(self)):
            for j in range(i ,len(self)):
                if i == j:
                    continue
                dist[i] = ( np.linalg.norm(self[i].com - self[j].com) )
        dist.sort()
        return dist

    def __eq__(self, other):
        """docstring for __eq__ """
        if not len(self) == len(other):
            return False
        for i, (m1, m2) in enumerate( zip(self, other) ):
            if m1 != m2:
                return False
        return True
        
    def get_qm_xyz_string(self, AA = False):
# If basis len is more than one, treat it like molecular ano type
# Where first element is for first row of elements

        st = "%d\n\n" % sum( [ len(m) for m in self if m.in_qm ] )
        for i in [all_el for mol in self for all_el in mol if mol.in_qm]:
            st += "{0:5s}{1:10.5f}{2:10.5f}{3:10.5f}\n".format( i.element, i.x, i.y, i.z )
        return st
    
    @property
    def p(self):
        if self.Property:
            el_dip = np.array([ (at.r-self.coc)*at.Property['charge'] for mol in self for at in mol])
            nuc_dip = np.array([ (at.r-self.coc)*charge_dict[at.element] for mol in self for at in mol])
            dip_lop = np.array([at.Property['dipole'] for mol in self for at in mol])
            dip = el_dip + nuc_dip
            return (dip + dip_lop) .sum(axis=0)

        return np.array([at.r*at.q for mol in self for at in mol]).sum(axis=0)



# Specifi

    @property
    def coc(self):
        if self.Property:
            pass
    #obj should be atom
        return sum( [at.r * charge_dict[at.element] for mol in self for at in mol])\
                /sum( map(float,[charge_dict[at.element] for mol in self for at in mol]) )


    def plot(self, copy= True, center = True ):
        """
Plot Cluster a 3D frame in the cluster

.. code:: python

    >>> m = Cluster()
    >>> m.add_atom( Atom(element = 'H', x = 1, z = 1) )
    >>> m.add_atom( Atom(element = 'H', x =-1, z = 1) )
    >>> m.add_atom( Atom(element = 'O', z = 0) )
    >>> m.plot()
    
"""

#Make a copy in order to not change original, and perform plot on it
        if copy:
            copy = deepcopy( self )
        else:
            copy = self
        if center:
            copy.translate([0,0,0])

        for mol in [mol for mol in copy if isinstance( mol, Molecule) ]:
            mol.populate_bonds()

#Plot in nice xyz axis
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d' )

#Plot bonds
        for mol in [mol for mol in copy if isinstance( mol, Molecule) ]:
            for atom in mol:
                for key in mol.bond_dict[ atom ]:
                    ax.plot( [key.x, atom.x],
                             [key.y, atom.y],
                             [key.z, atom.z], color = 'black' )



        ax.plot( [0, 1, 0, 0, 0, 0], [0,0 ,0,1,0,0], [0,0,0,0,0,1] )
        ax.text( 1.1, 0, 0, "X", color = 'red' )
        ax.text( 0, 1.1, 0, "Y", color = 'red' )
        ax.text( 0, 0, 1.1, "Z", color = 'red' )

        for i in copy:
            for j in i:
                ax.plot( [j.x], [j.y], [j.z], j.Molecule.style[j.element], linewidth= j.Molecule.linewidth[j.element] )
        ax.set_zlim3d( -5,5)
        plt.xlim(-5,5)
        plt.ylim(-5,5)
        plt.show()



    def get_qm_mol_string(self, basis = ("ano-1 2 1", "ano-1 3 2 1", "ano-2 5 4 1" ) , AA = False):
# If basis len is more than one, treat it like molecular ano type
# Where first element is for first row of elements

        if len( basis ) > 1:
            # Set row index number to periodic table one
            el_to_rowind = {"H" : 0, "C" : 1, "O" : 1, "N" : 1 , "S" : 2  }
        else:
            # Keep all 0, since basis is only len 1
            el_to_rowind = {"H" : 0, "C" : 0, "O" : 0, "N" : 0, "S" : 0 }

        st = ""
        comm1 = "QM: " + " ".join( [ str(m) for m in self if m.in_qm] )[:72]
        comm2 = "MM: " + " ".join( [ str(m) for m in self if m.in_mm] )[:73]
        uni = Molecule.unique([ at.element for mol in self for at in mol if mol.in_qm])
        s_ = ""
        if AA: s_ += "Angstrom"

        st += "ATOMBASIS\n%s\n%s\nAtomtypes=%d Charge=0 Nosymm %s\n" %( \
                comm1,
                comm2,
                len(uni),
                s_)
        for el in uni:
            st += "Charge=%s Atoms=%d Basis=%s\n" %( str(charge_dict[el]),
                    len( [all_el for mol in self for all_el in mol if ((all_el.element == el) and mol.in_qm )] ),
                     basis[ el_to_rowind[el] ] )
            for i in [all_el for mol in self for all_el in mol if ((all_el.element == el) and mol.in_qm) ]:
                st += "{0:5s}{1:10.5f}{2:10.5f}{3:10.5f}\n".format( i.element, i.x, i.y, i.z )
        return st
# Specific output for PEQM calculation in dalton, all molecules exclude itself
    def get_pe_pot_string( self, max_l = 1, pol = 2, hyp = 0, out_AA = False ):
        self.order_mm_atoms()
        st = r'!%s' % (self ) + '\n'
        st += r'@COORDINATES' + '\n'
        st += '%d\n' % sum([len(i) for i in self if i.in_mm ])
        if out_AA:
            st += "AA\n"
        else:
            st += "AU\n"
        #st += '%d\n' %len(mol)
        for mol in [m for m in self if m.in_mm]:
            for at in mol:
                st += "%s %.5f %.5f %.5f\n" % (at.number, \
                        at.x, at.y, at.z )

        st += r'@MULTIPOLES'  + '\n'
        if max_l >= 0:
            st += 'ORDER 0\n'
            st += '%d\n' % sum([len(i) for i in self if i.in_mm ])
            for mol in [m for m in self if m.in_mm]:
                for at in mol:
                    st += "%s %.5f\n" % (tuple( [at.number] ) + tuple( at.Property["charge"] )  )
        if max_l >= 1:
            st += 'ORDER 1\n'
            st += '%d\n' % sum([len(i) for i in self if i.in_mm ])
            for mol in [m for m in self if m.in_mm]:
                for at in mol:
                    st += "%s %.5f %.5f %.5f\n" % ( tuple([at.number]) + tuple(at.Property["dipole"])) 

        st += r'@POLARIZABILITIES' + '\n'
        st += 'ORDER 1 1\n'
        st += '%d\n' % sum([len(i) for i in self if i.in_mm ])
        if pol % 2 == 0:
            for mol in [m for m in self if m.in_mm]:
                #st += 'ORDER 1 1\n'
                #st += '%d\n' % len( mol )
                for at in mol:
                    st += "%s %.5f %.5f %.5f %.5f %.5f %.5f\n" % ( tuple([at.number]) + tuple(at.Property["alpha"])) 

        st += 'EXCLISTS\n%d %d\n' %( sum([len(i) for i in self if i.in_mm ])
 , len(mol))
        for mol in [m for m in self if m.in_mm]:
            for each in mol.exclists():
                ls = ""
                for ind in each:
                    ls += "%s " %ind
                ls += '\n'
                st += ls

        return st
# This is the old *QMMM input style in dalton, also valid for PointDipoleList
    def get_qmmm_pot_string( self, max_l = 1,
            pol = 22,
            hyp = 1,
# If complicated molecule, set dummy_pd to a coordinate to place the net property
            dummy_pd = False,
#Set ignore_qmmm to false to only write qmmm .pot file for molecues in mm region
            ignore_qmmm = True ):

# We need to check that it is not in LoProp mode
        if dummy_pd:
            assert self.LoProp == False

        if self.AA:
            st = "AA\n"
        else:
            st = "AU\n"
# Old qmmm format requires integer at end to properly read charges
        if ignore_qmmm:
            st += "%d %d %d %d\n" % (sum([len(i) for i in self ]), 
                    max_l, pol, hyp )
            st += "".join( [at.potline(max_l, pol, hyp) for mol in self for at in mol ] )
        else:
            st += "%d %d %d %d\n" % (sum([len(i) for i in self if i.in_mm ]), 
                    max_l, pol, hyp )
            st += "".join( [at.potline(max_l, pol, hyp) for mol in self for at in mol if mol.in_mm] )
        return st

    def get_xyz_string(self, ):
        st = "%d\n\n" % sum([len(i) for i in self ])
        for mol in self:
            for i in mol:
                st += "{0:10s} {1:10f} {2:10f} {3:10f}\n".format(\
                        i.element, i.x,  i.y , i.z )
        return st

    def get_xyz_string(self, both= False, qm_region = False, mm_region = False ):
        ats = []
        if qm_region:
            st = "%d\n\n" % sum([len(i) for i in self if i.in_qm ])
            ats = [at for mol in self for at in mol if mol.in_qm]
        if mm_region:
            st = "%d\n\n" % sum([len(i) for i in self if i.in_mm ])
            ats = [at for mol in self for at in mol if mol.in_mm]
        if qm_region and mm_region:
            st = "%d\n\n" % sum([len(i) for i in self if i.in_qmmm ])
            ats = [at for mol in self for at in mol if mol.in_qmmm]
        if both:
            ats = [at for mol in self for at in mol ]
        st = "%d\n\n" %len(ats)
        for i in ats:
            st += "{0:10s} {1:10f} {2:10f} {3:10f}\n".format(\
                    i.element, i.x,  i.y , i.z )
        return st

    def order_mm_atoms(self):
        cnt = 1
        for mol in [m for m in self if m.in_mm]:
            for at in mol:
                at.number = str(cnt)
                cnt += 1

    def update_water_props(self, model = "TIP3P",
            method = "HF", basis = "ANOPVDZ", dist = True,
            freq = "0.0"):
        from template import Template

        kwargs_dict = Template().get( *(model, method, basis,
            dist , freq ))
        for wat in self:
            t1, t2, t3 = wat.get_euler()
            for at in wat:
                Property.add_prop_from_template( at, kwargs_dict )
                at.Property.transform_ut_properties( t1, t2, t3)


    @staticmethod
    def get_water_cluster( fname , in_AA = False, out_AA = False , N_waters = 1000 ):
        """
Return a cluster of water molecules given file.

.. code:: python

    >>> c = Cluster.get_water_cluster( 'somefile.mol' , in_AA = False, out_AA = False, N_waters = 10 )
    >>> print len( c )
    10

"""
        atoms = []
        c = Cluster()
        if fname.endswith( ".xyz" ) or fname.endswith(".mol"):
            pat_xyz = re.compile(r'^\s*(\w+)\s+(-*\d*.+\d+)\s+(-*\d*.+\d+)\s+(-*\d*.+\d+) *$')
            for i in open( fname ).readlines():
                if pat_xyz.match(i):
                    f = pat_xyz.match(i).groups()
                    matched = pat_xyz.match(i).groups()
                    kwargs = { "element" :  matched[0], "x" : matched[1],
                            "y" : matched[2], "z" : matched[3] }
                    tmpAtom = Atom( **kwargs )
                    atoms.append( tmpAtom )

        elif fname.endswith( ".pdb" ):
            pat1 = re.compile(r'^(ATOM|HETATM)')
#Temporary atom numbering so that it is compatible with PEQM reader in dalton
            for i in open( fname ).readlines():
                if pat1.search(i):
                    if ( i[11:16].strip() == "SW") or (i[11:16] == "DW") \
                            or (i[11:16].strip() == "MW"):
                        continue
                    kwargs = {
                            "AA" : in_AA,
                            "x" : float(i[30:38].strip()),
                            "y" : float(i[38:46].strip()),
                            "z" : float(i[46:54].strip()),
                            "element": i[11:16].strip()[0],
                            "number" : i[6:11].strip()  }
                    tmpAtom = Atom( **kwargs )
                    atoms.append( tmpAtom )
        elif fname.endswith( ".out" ):
            pat_xyz = re.compile(r'^(\w+)\s+(-*\d*.+\d+)\s+(-*\d*.+\d+)\s+(-*\d*.+\d+) *$')
            for i in open( fname ).readlines():
                if pat_xyz.match(i):
                    f = pat_xyz.match(i).groups()
                    tmpAtom = Atom(f[0][0], float(f[1]), float(f[2]), float(f[3]), 0)
                    atoms.append( tmpAtom )
        elif fname.endswith( '.log' ):
            pat_atoms = re.compile ( r'NAtoms=\s+(\d+)' )
            pat_xyz = re.compile ( r'Standard ori' )
            lines = open(fname).readlines()
            conf = []
            for line in lines:
                if pat_atoms.search( line ):
                    N = int(pat_atoms.search( line ).group(1))
                    break
            for ind, line in enumerate(lines):
                if pat_xyz.search( line ):
                    conf.append( "\n".join( map( lambda x:x.strip('\n'), lines[ ind +5 : ind + 5 + N ]) ) )
            for each in conf[-1].split('\n'):
                spl = each.split()
                tmpAtom = Atom( element = elem_array[ int(spl[1]) ],
                        AA = True,
                        x = float(spl[3]),
                        y = float(spl[4]),
                        z = float(spl[5]),)
                atoms.append( tmpAtom )

#loop over oxygen and hydrogen and if they are closer than 1 A add them to a water
        waters = []
        cnt = 1
        if fname.endswith(".log") or fname.endswith( ".xyz" ) or fname.endswith(".mol"):
            xmin = 10000.0; ymin = 10000.0; zmin = 10000.0; 
            xmax = -10000.0; ymax = -10000.0; zmax = -10000.0; 
            for i in atoms:
                if i.x < xmin:
                    xmin = i.x
                if i.y < ymin:
                    ymin = i.y
                if i.z < zmin:
                    zmin = i.z
                if i.x > xmax:
                    xmax = i.x
                if i.y > ymax:
                    ymax = i.y
                if i.z > zmax:
                    zmax = i.z
            center = np.array([ xmax - xmin, ymax -ymin, zmax- zmin]) /2.0
            for i in atoms:
                if i.element == "H":
                    continue
                if i.in_water:
                    continue
                tmp = Water( AA = in_AA)
#Gaussian output seems to have Angstrom always
                if fname.endswith( '.log' ):
                    tmp.AA = True
                i.in_water = True
                tmp.append( i )
                for j in atoms:
                    if j.element == "O":
                        continue
                    if j.in_water:
                        continue
#If in angstrom
                    if in_AA:
                        if i.dist_to_atom(j) < 1.1:
                            tmp.append ( j )
                            j.in_water = True
                    else:
                        if i.dist_to_atom(j) < 1.1/a0:
                            tmp.append ( j )
                            j.in_water = True
                tmp.res_id = cnt
                cnt += 1
                waters.append( tmp )
            waters.sort( key = lambda x: x.dist_to_point( center ))
            center_water = waters[0]
            cent_wlist = waters[1:]
            cent_wlist.sort( key= lambda x: x.dist_to_water( center_water) )

            if N_waters < 1:
                print "WARNING ; chose too few waters in Cluster.get_water_cluster"
                raise SystemExit
# Ensure that cluster has ordered water structure from first index
            waters = [center_water] + cent_wlist[ 0 : N_waters - 1 ]
            for i in waters:
                c.append(i)
        elif fname.endswith( ".pdb" ):
#Find out the size of the box encompassing all atoms
            xmin = 10000.0; ymin = 10000.0; zmin = 10000.0; 
            xmax = -10000.0; ymax = -10000.0; zmax = -10000.0; 
            for i in atoms:
                if i.x < xmin:
                    xmin = i.x
                if i.y < ymin:
                    ymin = i.y
                if i.z < zmin:
                    zmin = i.z
                if i.x > xmax:
                    xmax = i.x
                if i.y > ymax:
                    ymax = i.y
                if i.z > zmax:
                    zmax = i.z
            center = np.array([ xmax - xmin, ymax -ymin, zmax- zmin]) /2.0
            wlist = []
            for i in atoms:
                if i.element == "H":
                    continue
                if i.in_water:
                    continue
                tmp = Water( AA = in_AA )
#__Water__.append() method will update the waters residue number and center coordinate
#When all atoms are there
#Right now NOT center-of-mass
                i.in_water= True
                tmp.append(i)
                for j in atoms:
                    if j.element == "O":
                        continue
                    if j.in_water:
                        continue
#1.05 because sometimes spc water lengths can be over 1.01
                    if in_AA:
                        if i.dist_to_atom(j) <= 1.05:
                            j.in_water = True
                            tmp.append( j )
                    else:
                        if i.dist_to_atom(j) <= 1.05/a0:
                            j.in_water = True
                            tmp.append( j )
                tmp.res_id = cnt
                cnt += 1
                wlist.append( tmp )

            wlist.sort( key = lambda x: x.dist_to_point( center ))
            center_water = wlist[0]
            cent_wlist = wlist[1:]
            cent_wlist.sort( key= lambda x: x.dist_to_water( center_water) )


            if N_waters < 1:
                print "WARNING ; chose too few waters in Cluster.get_water_cluster"
                raise SystemExit

# Ensure that cluster has ordered water structure from first index
            waters = [center_water] + cent_wlist[ 0 : N_waters - 1 ]
            for i in waters:
                c.append(i)
        elif fname.endswith( ".out" ):
            for i in atoms:
                if i.element == "H":
                    continue
                if i.in_water:
                    continue
                tmp = Water()
                i.in_water = True
                tmp.append( i )
                for j in atoms:
                    if j.element == "O":
                        continue
                    if j.in_water:
                        continue
#If in cartesian:
                    if i.AA:
                        if i.dist_to_atom(j) < 1.0:
                            tmp.append ( j )
                            j.in_water = True
                    else:
                        if i.dist_to_atom(j) < 1.0/a0:
                            tmp.append ( j )
                            j.in_water = True
                tmp.res_id = cnt
                cnt += 1
                waters.append( tmp )
        for wat in c:
            for atom in wat:
                atom._res_id = wat.res_id

        if in_AA or fname.endswith( '.log' ):
            if not out_AA:
                for wat in c:
                    wat.to_AU()
        if not in_AA:
            if out_AA:
                for wat in c:
                    wat.to_AA()
        for wat in c:
            wat.o.order = 1
            wat.h1.order = 2
            wat.h2.order = 3
        c.set_qm_mm(100)
        return c


    def mol_too_close(self, mol, dist = 2.5):
        for mols in self:
            for ats in mols:
                for at in mol:
                    if at.dist_to_atom( ats ) < dist:
                        return True
        return False

    def attach_properties(self, 
            model = "TIP3P",
            method = "HF",
            basis = "ANOPVDZ",
            loprop = True,
            freq = "0.0"):
        """
Attach property to all atoms and oxygens, by default TIP3P/HF/ANOPVDZ, static
        """
        templ = Template().get( *(model, method, basis, loprop, freq) )
        for mol in self:
            for at in mol:
                Property.add_prop_from_template( at, templ )
            t1, t2, t3 = mol.get_euler()
            for at in mol:
                at.Property.transform_ut_properties( t1, t2, t3 )
            if loprop:
                mol.LoProp = True
            else:
                mol.LoProp = False
        self.Property = True

    def add(self, item ):
        if isinstance( mol , Molecule ):
            self.add_mol( item )
        else:
            self.add_atom( item )
    def add_mol(self, mol, in_mm = False, in_qm = False,
            in_qmmm = False, *args, **kwargs):
        if isinstance( mol , Molecule ):
            mol.in_mm = in_mm
            mol.in_qm = in_qm
            mol.in_qmmm = in_qmmm
            super( Cluster, self ).append( mol, *args, **kwargs )
            mol.cluster = self
        elif type( mol ) == list:
            for each in mol:
                each.in_mm = in_mm
                each.in_qm = in_qm
                each.in_qmmm = in_qmmm
                super( Cluster, self ).append( each, *args, **kwargs )
                each.cluster = each

    def add_atom(self, *at):
        for i, iat in enumerate(at):
            self.append( iat )
            iat.cluster = self

    def set_qm_mm(self, N_qm = 1, N_mm = 0):
        """First set all waters to False for security """
        for i in self:
            i.in_qm = False
            i.in_mm = False

        """Set the first N_qm in qm region and rest N_mm in mm region"""
        for i in self[ 0 : N_qm  ]:
            i.in_qm = True
        for i in self[ N_qm  : N_qm + N_mm ]:
            i.in_mm = True
    def copy_cluster(self):
        tmp_c = Cluster()
        for res in self:
            tmp_c.add(res.copy_self())
        return tmp_c

    def get_inp_string(self, method ='B3LYP', basis = "6-31+g*", procs= 8):
        """Write gaussian .inp file for geometry optimization"""
        st = r"%" + "Nprocshared=%d\n" %procs
        st += r"%" + "Mem=20MW\n"
        st += "#p %s/%s opt " %(method,basis)
        if not self.AA:
            st += "units=au " 
        st += '\n\ncomment\n\n'
        st += "%d %d\n" %( self.sum_property['charge'][0], 1 )
        for i in [at for mol in self for at in mol]:
            st += "%s %.5f %.5f %.5f\n" %(i.element, i.x, i.y, i.z ) 
        st+= '\n\n\n'
        return st


    @property
    def com(self):
        if len(self) == 0:return np.zeros(3)
        return sum([at.r*at.mass for mol in self for at in mol]) / sum([at.mass for mol in self for at in mol] )

    @property
    def sum_property(self):
        """
Return the sum properties of all molecules in cluster
        """
        el_dip = np.array([ (at.r-self.coc)*at.Property['charge'] for mol in self for at in mol])
        nuc_dip = np.array([ (at.r-self.coc)*charge_dict[at.element] for mol in self for at in mol])
        dip_lop = np.array([at.Property['dipole'] for mol in self for at in mol])
        dip = el_dip + nuc_dip
        dip_tot = (dip + dip_lop).sum(axis=0)
        p = Property()
        for mol in self:
            for at in mol:
                p += at.Property
        p['dipole'] = dip_tot
        return p

    def to_AA(self):
        if not self.AA:
            for i in self:
                i.to_AA()

    def to_AU(self):
        if self.AA:
            for i in self:
                i.to_AU()

    def translate(self, r):
        """
Translate cluster center-of-mass to position r

.. code:: python

    >>> m = Cluster()
    >>> m.append( Atom(element = 'H', z = 1) )
    >>> m.append( Atom(element = 'H', z = 0) )
    >>> print m.com
    [0, 0, 0.5 ]
    >>> m.translate( [0, 3, 5] )
    >>> print m.com
    [0, 3, 5 ]
    
"""
        vec = r - self.com
        for at in [at for mol in self for at in mol]:
            at.x = vec[0] + at.x 
            at.y = vec[1] + at.y 
            at.z = vec[2] + at.z 
        return self

if __name__ == '__main__':
    from use_generator import *
    from gaussian import *
    m1 = Generator().get_mol(model = 'spc' )
    m2 = Generator().get_mol( center = [0,0, 10 ], model = 'spc' )
    m2.res_id = 2
    c = Cluster()
    c.add_mol(m1)
    c.add_mol(m2)
    
    t = Template().get( model = 'SPC' )
#    for m in [m1, m2]:
#        for at in m:
#            Property.add_prop_from_template( at, t )
    c.update_water_props( model = 'SPC', dist = True )
    g = GaussianQuadrupoleList.from_string( c.get_qmmm_pot_string( ignore_qmmm = True ) )
    g.solve_scf()
    print g.beta()

