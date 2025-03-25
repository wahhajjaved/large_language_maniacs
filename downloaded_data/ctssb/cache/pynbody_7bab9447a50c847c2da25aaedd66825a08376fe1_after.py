from . import snapshot, array, util
from . import family
from . import units

import struct
import numpy as np

class TipsySnap(snapshot.SimSnap) :
    def __init__(self, filename, only_header=False) :
	super(TipsySnap,self).__init__()
	
	self._filename = filename
	
	f = util.open_(filename)
	# factoring out gzip logic opens up possibilities for bzip2,
	# or other more advanced filename -> file object mapping later,
	# carrying this across the suite

	t, n, ndim, ng, nd, ns = struct.unpack("diiiii", f.read(28))
        if (ndim > 3 or ndim < 1):
            byteswap=True
            f.seek(0)
            t, n, ndim, ng, nd, ns = struct.unpack(">diiiii", f.read(28))

        # In non-cosmological simulations, what is t? Is it physical
        # time?  In which case, we need some way of telling what we
        # are dealing with and setting properties accordingly.
        self.properties['a'] = t
        self.properties['z'] = 1.0/t - 1.0

	assert ndim==3
	
	self._num_particles = ng+nd+ns
	f.read(4)

	# Store slices corresponding to different particle types
	self._family_slice[family.gas] = slice(0,ng)
	self._family_slice[family.dm] = slice(ng, nd+ng)
	self._family_slice[family.star] = slice(nd+ng, ng+nd+ns)

        
	self._create_arrays(["pos","vel"],3)
	self._create_arrays(["mass","eps","phi"])
	self.gas._create_arrays(["rho","temp","metals"])
	self.star._create_arrays(["metals","tform"])

	self.gas["temp"].units = "K" # we know the temperature is always in K
	# Other units will be set by the decorators later
	

	# Load in the tipsy file in blocks.  This is the most
	# efficient balance I can see for keeping IO contiguuous, not
	# wasting memory, but also not having too much python <-> C
	# interface overheads

	max_block_size = 1024 # particles

	# describe the file structure as list of (num_parts, [list_of_properties]) 
	file_structure = ((ng,family.gas,["mass","x","y","z","vx","vy","vz","rho","temp","eps","metals","phi"]),
			  (nd,family.dm,["mass","x","y","z","vx","vy","vz","eps","phi"]),
			  (ns,family.star,["mass","x","y","z","vx","vy","vz","metals","tform","eps","phi"]))
	

	self._decorate()
	
        if only_header == True :
            return 

	for n_left, type, st in file_structure :
	    n_done = 0
	    self_type = self[type]
	    while n_left>0 :
		n_block = max(n_left,max_block_size)

		# Read in the block
                if(byteswap):
                    g = np.fromstring(f.read(len(st)*n_block*4),'f').byteswap().reshape((n_block,len(st)))
                else:
                    g = np.fromstring(f.read(len(st)*n_block*4),'f').reshape((n_block,len(st)))
                    
		# Copy into the correct arrays
		for i, name in enumerate(st) :
		    self_type[name][n_done:n_done+n_block] = g[:,i]

		# Increment total ptcls read in, decrement ptcls left of this type
		n_left-=n_block
		n_done+=n_block


	

    def loadable_keys(self) :
	"""Produce and return a list of loadable arrays for this TIPSY file."""

	def is_readable_array(x) :
	    try:
		f = util.open_(x)
		return int(f.readline()) == len(self)
	    except (IOError, ValueError) :
                # could be a binary file
                f.seek(0)
                
                buflen = len(f.read())
                
                if (buflen-4)/4/3. == len(self) : # it's a float vector 
                    return True
                elif (buflen-4)/4. == len(self) : # it's a float array 
                    return True
                else :
                    return False

	    
	import glob

        if len(self._loadable_keys_registry) == 0 :
            
            name = util.cutgz(self._filename)
            
            fs = glob.glob(name+".*")
            
            res =  map(lambda q: q[len(name)+1:], filter(is_readable_array, fs))
            for i,n in enumerate(res): res[i] = util.cutgz(n)

            self._loadable_keys_registry['From files'] = res
            self._loadable_keys_registry['To compute'] = snapshot.SimSnap.loadable_keys(self)

            for type in self._loadable_keys_registry: self._loadable_keys_registry[type].sort(key=str.lower)
            
            self._loadable_keys_registry.__repr__ = self._print_loadable_keys_registry
            
        return self._loadable_keys_registry
	
    
    def _read_array(self, array_name, fam=None, filename = None,
        packed_vector = None) :
        """Read a TIPSY-ASCII or TIPSY-BINARY auxiliary file with the
        specified name. If fam is not None, read only the particles of
        the specified family."""

        import sys, os
	
	# N.B. this code is a bit inefficient for loading
	# family-specific arrays, because it reads in the whole array
	# then slices it.  But of course the memory is only wasted
	# while still inside this routine, so it's only really the
	# wasted time that's a problem.


        # determine whether the array exists in a file

        if filename is None :
            if self._filename[-3:] == '.gz' :
                filename = self._filename[:-3]+"."+array_name
            else :
                filename = self._filename+"."+array_name
                
            if not os.path.isfile(filename) :
                filename+=".gz"

        
        f = util.open_(filename)
        

        # if we get here, we've got the file - try loading it

        try :
            l = int(f.readline())

        except ValueError :
            # this is probably a binary file
            import xdrlib
            binary = True

            f.seek(0)
            up = xdrlib.Unpacker(f.read())
            l = up.unpack_int()

            buflen = len(up.get_buffer())

            if (buflen-4)/4/3. == l : # it's a float vector 
                data = np.array(up.unpack_farray(l*3,up.unpack_float))
                ndim = 3
            elif (buflen-4)/4. == l : # it's a float array 
                data = np.array(up.unpack_farray(l,up.unpack_float))
                ndim = 1
            else: # don't know what it is
                raise IOError, "Incorrect file format"
        else:
            binary = False

            if l!=len(self) :
                raise IOError, "Incorrect file format"

            # Inspect the first line to see whether it's float or int
            l = "0\n"
            while l=="0\n" : l = f.readline()
            if "." in l or "e" in l :
                tp = float
            else :
                tp = int

            # Restart at head of file
            f.seek(0)

            f.readline()
            data = np.fromfile(f, dtype=tp, sep="\n")
            ndim = len(data)/len(self)

            if ndim*len(self)!=len(data) :
                raise IOError, "Incorrect file format"

        if ndim>1 :
            dims = (len(self),ndim)

            # check whether the vector format is specified in the param file
            # this only matters for binary because ascii files use packed vectors by default
            if (binary) and (packed_vector == None) :
                # default bPackedVector = 0, so must use column-major format when reshaping
                v_order = 'F'
                if self._paramfile != "" :
                    try:
                        if int(self._paramfile.get("bPackedVector",0)) :
                            v_order="C"
                    except ValueError :
                        pass
                    
            elif (packed_vector is True) or (binary is False) :
                v_order = 'C'
            else :
                v_order = 'F'
        else :
            dims = len(self)
            v_order = 'C'


        if fam is None :
            self._arrays[array_name] = data.reshape(dims, order=v_order).view(array.SimArray)
            self._arrays[array_name].sim = self
        else :
            self._create_family_array(array_name, fam, ndim, data.dtype)
            self._get_family_array(array_name, fam)[:] = \
                                           data.reshape(dims,order=v_order).view(array.SimArray)[self._get_family_slice(fam)]
            self._get_family_array(array_name, fam).sim = self
            

	
    @staticmethod
    def _can_load(f) :
	# to implement!
	return True

@TipsySnap.decorator
def load_paramfile(sim) :
    import sys, os, glob
    x = os.path.abspath(sim._filename)
    done = False
    sim._paramfile = {}
    filename=None
    for i in xrange(2) :
        x = os.path.dirname(x)
	l = glob.glob(os.path.join(x,"*.param"))

	for filename in l :
	    # Attempt the loading of information
	    try :
		f = file(filename)
	    except IOError :
		continue
	    
            
            for line in f :
		try :
                    if line[0]!="#" :
                        s = line.split()
                        sim._paramfile[s[0]] = " ".join(s[2:])
                                
		except IndexError, ValueError :
		    pass

            if len(sim._paramfile)>1 :
                sim._paramfile["filename"] = filename
                done = True
                
        if done : break

            

@TipsySnap.decorator
def param2units(sim) :
    import sys, math, os, glob

    munit = dunit = hub = None
    
    try :
        munit_st = sim._paramfile["dMsolUnit"]+" Msol"
        munit = float(sim._paramfile["dMsolUnit"])
        dunit_st = sim._paramfile["dKpcUnit"]+" kpc"
        dunit = float(sim._paramfile["dKpcUnit"])
        hub = float(sim._paramfile["dHubble0"])
        om_m0 = float(sim._paramfile["dOmega0"])
        om_lam0 = float(sim._paramfile["dLambda"])

    except KeyError :
        pass

    if munit is None or dunit is None :
        return


    denunit = munit/dunit**3
    denunit_st = str(denunit)+" Msol kpc^-3"

    #
    # the obvious way:
    #
    #denunit_cgs = denunit * 6.7696e-32
    #kpc_in_km = 3.0857e16
    #secunit = 1./math.sqrt(denunit_cgs*6.67e-8)
    #velunit = dunit*kpc_in_km/secunit

    # the sensible way:
    # avoid numerical accuracy problems by concatinating factors:
    velunit = 8.0285 * math.sqrt(6.67e-8*denunit) * dunit   
    velunit_st = ("%.5g"%velunit)+" km s^-1"

    #You have: kpc s / km
    #You want: Gyr
    #* 0.97781311
    timeunit = dunit / velunit * 0.97781311
    timeunit_st = ("%.5g"%timeunit)+" Gyr"

    enunit_st = "%.5g km^2 s^-2"%(velunit**2)

    if hub!=None:
        hubunit = 10. * velunit / dunit
        hubunit_st = ("%.3f"%(hubunit*hub))

        # append dependence on 'a' for cosmological runs
        dunit_st += " a"
        denunit_st += " a^-3"
        velunit_st += " a"

        # Assume the box size is equal to the length unit
        sim.properties["boxsize"] = units.Unit(dunit_st)


    sim["vel"].units = velunit_st
    sim["phi"].units = sim["vel"].units**2
    sim["eps"].units = dunit_st
    sim["pos"].units = dunit_st
    sim.gas["rho"].units = denunit_st
    sim["mass"].units = munit_st
    sim.star["tform"].units = timeunit_st

    sim.gas["metals"].units = ""
    sim.star["metals"].units = ""

    sim._file_units_system = [sim["vel"].units, sim["mass"].units, sim["pos"].units]

    if hub!=None:
        sim.properties['h'] = hubunit*hub
        sim.properties['omegaM0'] = float(om_m0)
        sim.properties['omegaL0'] = float(om_lam0)


def _abundance_estimator(metal) :

    Y_He = ((0.236+2.1*metal)/4.0)*(metal<=0.1)
    Y_He+= ((-0.446*(metal-0.1)/0.9+0.446)/4.0)*(metal>0.1)
    Y_H = 1.0-Y_He*4. - metal

    return Y_H, Y_He

@TipsySnap.derived_quantity
def HII(sim) :
    """Number of HII ions per proton mass"""
    Y_H, Y_He = _abundance_estimator(sim["metals"])
    return Y_H - sim["HI"]

@TipsySnap.derived_quantity
def HeIII(sim) :
    """Number of HeIII ions per proton mass"""
    Y_H, Y_He = _abundance_estimator(sim["metals"])
    return Y_He-sim["HeII"]-sim["HeI"]

@TipsySnap.derived_quantity
def ne(sim) :
    """Number of electrons per proton mass"""
    return sim["HII"] + sim["HeII"] + 2*sim["HeIII"]
    
@TipsySnap.derived_quantity
def mu(sim) :
    """Relative atomic mass, i.e. number of particles per
    proton mass, ignoring metals (since we generally only know the
    mass fraction of metals, not their specific atomic numbers)"""
    
    x =  sim["HI"]+2*sim["HII"]+sim["HeI"]+2*sim["HeII"]+3*sim["HeIII"]
    
    x._units = 1/units.m_p
    return x
    
@TipsySnap.derived_quantity
def u(sim) :
    """Specific Internal energy"""
    u = (3./2) * units.k * sim["temp"] # per particle
    u=u*sim["mu"] # per unit mass
    u.convert_units("eV m_p^-1")
    return u

@TipsySnap.derived_quantity
def p(sim) :
    """Pressure"""
    p = sim["u"]*sim["rho"]*(2./3)
    p.convert_units("dyn")
    return p
