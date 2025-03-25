"""Class for FEHM data"""

"""
Copyright 2013.
Los Alamos National Security, LLC. 
This material was produced under U.S. Government contract DE-AC52-06NA25396 for 
Los Alamos National Laboratory (LANL), which is operated by Los Alamos National 
Security, LLC for the U.S. Department of Energy. The U.S. Government has rights 
to use, reproduce, and distribute this software.  NEITHER THE GOVERNMENT NOR LOS 
ALAMOS NATIONAL SECURITY, LLC MAKES ANY WARRANTY, EXPRESS OR IMPLIED, OR ASSUMES 
ANY LIABILITY FOR THE USE OF THIS SOFTWARE.  If software is modified to produce 
derivative works, such modified software should be clearly marked, so as not to 
confuse it with the version available from LANL.

Additionally, this library is free software; you can redistribute it and/or modify 
it under the terms of the GNU Lesser General Public License as published by the 
Free Software Foundation; either version 2.1 of the License, or (at your option) 
any later version. Accordingly, this library is distributed in the hope that it 
will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of 
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General 
Public License for more details.
"""

import numpy as np
from copy import copy, deepcopy
import os,time,platform,shutil
from subprocess import Popen
from time import sleep
try:
	from matplotlib import pyplot as plt
	from mpl_toolkits.mplot3d import axes3d
except ImportError:
	'placeholder'

from fgrid import*
from fvars import*
from fpost import*
from fdflt import*
from fhelp import*

dflt = fdflt()

WINDOWS = platform.system()=='Windows'
if WINDOWS: copyStr = 'copy'; delStr = 'del'; slash = '\\'
else: copyStr = 'cp'; delStr = 'rm'; slash = '/'

# list of macros that might be encountered
fdata_sections = ['cont','pres','zonn','zone','cond','time','ctrl','iter','rock','perm',
					'boun','flow','strs','text','sol','nfin','hist','node','carb','rlp','grad','nobr',
					'flxz','rlpm','hflx','trac','vcon','ppor','vapl','adif','ngas','flxo']
# list of potential CONTOUR output variables
contour_variables=[['strain','stress'],
				   ['co2'],
				   ['vapor','dp','grid','capillary','density','displacement','fhydrate','flux','permeability','porosity','source','velocity','wt','zid'],
				   ['formatted','material','liquid','geo','nodit','concentration','head','pressure','saturation','temperature','xyz','zone']]
# list of potential HISTORY output variables
history_variables=['deg','temperature','mpa','pressure','head','meters','feet','saturation','wco','flow','kgs',
				   'enthalpy','efl','mjs','density','humidity','viscosity','zflux','concentration','wt','co2s',
				   'co2sl','co2sg','co2m','co2mt','co2mf','co2md','cfluxz','displacements','disx','disy','disz',
				   'stress','strsx','strsy','strsz','strsxy','strsxz','strsyz','strain','rel','global']
# dictionary of perm model parameters, indexed by perm model number, ORDER OF LIST MUST EQUAL ORDER OF INPUT
permDicts = dict((
	(1,[]),
	
	(21,['nx','ny','nz','frict_coef','cohesion','pore_press_factor','tau_ex_ramp_range',
	'yngs_mod_mult_x','yngs_mod_mult_y','yngs_mod_mult_z','perm_mult_x','perm_mult_y','perm_mult_z']),
	
	(22,['frict_coef','cohesion','pore_press_factor','tau_ex_ramp_range','yngs_mod_mult_x','yngs_mod_mult_y',
	'yngs_mod_mult_z','perm_mult_x','perm_mult_y','perm_mult_z','por_mult','perm_incremental','tau_ex_init']),
	
	(24,['shear_frac_tough','static_frict_coef','dynamic_frict_coef','frac_num','onset_disp',
	'disp_interval','max_perm_change','frac_cohesion','frac_dens']),
	
	(25,['frac_spacing','init_frac_aperture','norm_frac_tough','shear_frac_tough','frac_dilat_angle',
	'static_frict_coef','dynamic_frict_coef','frac_num','onset_disp','disp_interval','max_perm_change',
	'frac_cohesion','frac_dens']),
	))
# dictionary of perm model units, indexed by perm model number, ORDER OF LIST MUST EQUAL ORDER OF INPUT
permUnits = dict((
	(1,[]),
	(21,['','','','','MPa','','MPa','','','','','','']),
	(22,['','MPa','','MPa','','','','','','','','','MPa']),
	(24,['MPa/m','','','','m','m','log(m^2)','MPa','']),
	(25,['m','m','MPa/m','MPa/m','degrees','','','','m','m','log(m^2)','MPa','']),
	))
# dictionary of relative permeability model parameters, indexed by model number, ORDER OF LIST MUST EQUAL ORDER OF INPUT
rlpDicts = dict((
	(-1,['liq_rel_perm','vap_rel_perm','cap_pres_zero_sat','sat_zero_cap_pres']),
	(1,['resid_liq_sat','resid_vap_sat','max_liq_sat','max_vap_sat','cap_pres_zero_sat','sat_zero_cap_pres']),
	(2,['resid_liq_sat','resid_vap_sat','cap_pres_zero_sat','sat_zero_cap_pres']),
	(3,['resid_liq_sat','resid_vap_sat','inv_air_entry_head','power_exponent',
	'low_sat_fit_param','cutoff_sat']),
	(16,['resid_water_sat','max_water_sat','water_exp','resid_co2_sat','max_co2_sat','co2_exp',
	'co2_water_Pc_exp','co2_water_Pc_max']),
	(17,['resid_water_sat','max_water_sat','water_exp','resid_co2liq_sat','max_co2liq_sat','co2liq_exp',
	'co2gasliq_exp','resid_co2gas_sat','max_co2gas_sat','co2gas_exp','co2liq_water_Pc_exp','co2liq_water_Pc_max',
	'co2liq_co2gas_Pc_exp','co2liq_co2gas_Pc_max']),
	))
adsorptionDicts = dict((
	(0,['alpha1','alpha2','beta']),		# conservative solute
	(1,['alpha1','alpha2','beta']),		# linear sorption isotherm
	(2,['alpha1','alpha2','beta']),		# Freundlich sorption isotherm
	(3,['alpha1','alpha2','beta']),		# Modified Freundlich sorption isotherm
	(4,['alpha1','alpha2','beta']),		# Langmuir sorption isotherm
	))
diffusionDicts = dict((
	(0,['diffusion','dispersion_x','dispersion_y','dispersion_z']),		# molecular diffusion coefficient is constant
	(1,['diffusion','dispersion_x','dispersion_y','dispersion_z']),		# Millington Quark diffusion model
	(2,['diffusion','dispersion_x','dispersion_y','dispersion_z']),		# Conca Wright diffusion model
	(3,['diffusion','dispersion_x','dispersion_y','dispersion_z']),		# calculated from adif
	))
vconDicts = dict((
	(1,['T_ref','cond_ref','dcond_dT']),		# linear variation of thermal conductivity with temperature
	(2,['cond_s1','cond_s0']),					# square root variation of thermal conductivity with liquid saturation
	(3,['T_ref','cond_ref','exponent']),		# intact salt
	(4,['T_ref','cond_ref','coeff_phi4','coeff_phi3','coeff_phi2','coeff_phi1','coeff_phi0','exponent']), # crushed salt
	))
pporDicts = dict((
	(1,['compressibility']),		# aquifer compressibility
	(-1,['specific_storage']),					# specific storage
	(-2,['exponent','Px']),		# gangi model
	(7,['param1','param2','param3','param4']), 		# unknown - salt
	))
model_list = dict((('permmodel',permDicts),
		('rlp',rlpDicts),
		('vcon',vconDicts),
		('ppor',pporDicts),
		('adsorption',adsorptionDicts),
		('diffusion',diffusionDicts)))
model_titles = dict((('rlp','RELATIVE PERMEABILITY'),
					 ('permmodel',''),
					 ('vcon','VARIABLE THERMAL CONDUCTIVITY'),
					 ('ppor','VARIABLE POROSITY'),
					 ('dispersion',''),
					 ('adsorption',''),
					 ))
# list of macros
fpres = (('pressure',None),('temperature',None),('saturation',None))
fperm = (('kx',None),('ky',None),('kz',None))
fcond = (('cond_x',None),('cond_y',None),('cond_z',None))
fflow = (('rate',None),('energy',None),('impedance',None))
frock = (('density',None),('specific_heat',None),('porosity',None))
fgrad = (('reference_coord',None),('direction',None),('variable',None),('reference_value',None),('gradient',None))
fbiot = (('thermal_expansion',None),('pressure_coupling',None))
felastic = (('youngs_modulus',None),('poissons_ratio',None))
fco2frac = (('water_rich_sat',None),('co2_rich_sat',None),('co2_mass_frac',None),('init_salt_conc',None),('override_flag',None))
fco2flow = (('rate',None),('energy',None),('impedance',None),('bc_flag',None))
fco2diff = (('diffusion',None),('tortuosity',None))
fco2pres = (('pressure',None),('temperature',None),('phase',None))
fstressboun = (('value',None),('direction',None))
fhflx = (('heat_flow',None),('multiplier',None))
ftpor = (('tracer_porosity',None),)

macro_list = dict((('pres',fpres),('perm',fperm),('cond',fcond),('flow',fflow),('rock',frock),
			('biot',fbiot),('elastic',felastic),('co2frac',fco2frac),('co2flow',fco2flow),
			('co2pres',fco2pres),('co2diff',fco2diff),
			#('permmodel',fpermmodel),
			#	('rlp',frlp),
			('stressboun',fstressboun),('grad',fgrad),('hflx',fhflx),('tpor',ftpor)))
			
# potential nodal properties
node_props = ('kx','ky','kz','cond_x','cond_y','cond_z','density','specific_heat','porosity','thermal_expansion','pressure_coupling',
'youngs_modulus','poissons_ratio')
node_gen = ('rate','energy','impedance')
macro_titles = dict((('pres','INITIAL TEMPERATURE AND PRESSURE'),
					 ('perm','PERMEABILITY'),
					 ('cond','ROCK CONDUCTIVITY'),
					 ('flow','GENERATORS'),
					 ('hflx',''),
					 ('rock','MATERIAL PARAMETERS'),
					 ('grad','INITIAL VARIABLE GRADIENTS'),
					 ('elastic',''),
					 ('biot',''),
					 ('co2flow',''),
					 ('co2frac',''),
					 ('co2pres',''),
					 ('co2diff',''),
					 ('stressboun',''),
#					 ('permmodel',''),
#					 ('rlp',''),
					 ('rlpm','RELATIVE PERMEABILITY'),
					 ('tpor',''),))
macro_descriptor = dict((('pres','Initial conditions'),
					 ('perm','Permeability'),
					 ('cond','Thermal conductivity properties'),
					 ('flow','Source or sink'),
					 ('rock','Material properties'),
					 ('grad','Initial condition gradients'),
					 ('elastic','Elastic properties'),
					 ('biot','Fluid-stress coupling properties'),
					 ('co2flow','CO2 source of sink'),
					 ('co2frac','CO2 fraction'),
					 ('co2pres','CO2 initial conditions'),
					 ('co2diff','CO2 diffusion properties'),
					 ('stressboun','Stress boundary condition'),
					 ('permmodel','Stress permeability relationship'),
					 ('rlp','Relative permeablity relationship'),
					 ('hflx','Heat flux boundary condition'),
					 ('tpor','Tracer porosity'),))
rlpm_dicts=dict((
	('constant',{}),
	('linear',(('minimum_saturation',0),('maximum_saturation',1))),
	('exponential',(('minimum_saturation',0),('maximum_saturation',1),('exponent',1),('maximum_relperm',1))),
	('corey',(('minimum_saturation',0),('maximum_saturation',1))),
	('brooks-corey',(('minimum_saturation',0),('maximum_saturation',1),('exponent',1))),
	('vg',(('minimum_saturation',0),('maximum_saturation',1),('air_entry_head',1),('exponent',1))),
	
	('linear_cap',(('cap_at_zero_sat',None),('sat_at_zero_cap',None))),
	('brooks-corey_cap',(('minimum_saturation',0),('maximum_saturation',1),('exponent',1),('capillary_entry_presure',0.01),
				('low_saturation_fitting',None),('cutoff_saturation',None))),
	('vg_cap',(('minimum_saturation',0),('maximum_saturation',1),('air_entry_head',1),('exponent',1),
				('low_saturation_fitting',None),('cutoff_saturation',None))),
	))
rlpm_cap1 = dict((('vg_cap','vg_cap'),('brooks-corey_cap','brooks-corey'),('linear_cap','linear_for')))
rlpm_cap2 = dict((('vg_cap','vg_cap'),('brooks-corey','brooks-corey_cap'),('linear_for','linear_cap')))
rlpm_phases = ['water','air','co2_liquid','co2_gas','vapor']

def _title_string(s,n): 						#prepends headers to sections of FEHM input file
	if not n: return
	ws = '# '
	pad = int(np.floor((n - len(s) - 2)/2))
	for i in range(pad): ws+='-'
	ws+=s
	for i in range(pad): ws+='-'
	ws+='\n'
	return ws
def _zone_ind(indStr): return abs(int(indStr))-(int(indStr)+abs(int(indStr)))/2
class fzone(object):						#FEHM zone object.
	"""FEHM Zone object.
	
	"""
	__slots__ = ['_index','_type','_points','_file','_name','_parent','_nodelist','_file','_permeability',
			'_conductivity','_density','_specific_heat','_porosity','_youngs_modulus','_poissons_ratio',
			'_thermal_expansion','_pressure_coupling','_Pi','_Ti','_Si','_fixedT','_fixedP','_updateFlag']
	def __init__(self,index=None,type='',points=[],nodelist=[],file='',name = ''):
		self._index=None
		if index != None: self._index = index
		self._type=''
		if type: self._type = type
		self._points=[]				
		if points: self._points=points
		self._file = ''				
		self._name = ''
		self._parent = None
		if name: self._name = name
		self._nodelist=[]
		if (self.type == 'nnum' or self.type == 'list') and nodelist:
			self._nodelist = nodelist
		if file: self._file = file
		# material properties
		self._permeability = None
		self._conductivity = None
		self._density = None
		self._specific_heat = None
		self._porosity = None
		self._youngs_modulus = None
		self._poissons_ratio = None
		self._thermal_expansion = None
		self._pressure_coupling = None
		self._Pi = None
		self._Ti = None
		self._Si = None
		self._fixedT = None
		self._fixedP = None
		self._updateFlag = True
	def __repr__(self): return 'zn'+str(self.index)	
	def _get_index(self): return self._index
	def _set_index(self,value): self._index = value
	index = property(_get_index,_set_index) #: (*int*) Integer number denoting the zone.
	def _get_type(self): return self._type
	def _set_type(self,value):
		oldtype = self._type
		self._type = value
		if self._type != oldtype:
			self._points = []
	type = property(_get_type,_set_type)	#: (*str*) String denoting the zone type. Default is 'rect', alternatives are 'list', 'nnum'
	def _get_name(self): return self._name
	def _set_name(self,value): self._name = value
	name = property(_get_name,_set_name)	#: (*str*) Name of the zone. Will appear commented beside the zone definition in the input file. Can be used to index the ``fdata.zone`` attribute.
	def _get_file(self): return self._file
	def _set_file(self,value): self._file=value
	file = property(_get_file,_set_file)	#: (*str*) File name if zone data is or is to be contained in a separate file. If file does not exist, it will be created and written to when the FEHM input file is being written out.
	def rect(self,p1,p2): 					#generates a rectangular zone based on corner coordinates
		"""Create a rectangular zone corresponding to the bounding box delimited by p1 and p2.
		
		:param p1: coordinate of first corner of the bounding box.
		:type p1: ndarray
		:param p2: coordinate of the second corner of the bounding box.
		:type p2: ndarray
		
		"""
		self.type='rect'
		if len(p1) == 2:
			xmax,xmin = np.max([p1[0],p2[0]]),np.min([p1[0],p2[0]])
			ymax,ymin = np.max([p1[1],p2[1]]),np.min([p1[1],p2[1]])
			self.points=[[xmin,xmax,xmax,xmin,xmin,xmax,xmax,xmin],
						 [ymax,ymax,ymin,ymin,ymax,ymax,ymin,ymin],
						 [0., 0., 0., 0., 0., 0., 0., 0.]]
		elif len(p1) == 3:
			xmax,xmin = np.max([p1[0],p2[0]]),np.min([p1[0],p2[0]])
			ymax,ymin = np.max([p1[1],p2[1]]),np.min([p1[1],p2[1]])
			zmax,zmin = np.max([p1[2],p2[2]]),np.min([p1[2],p2[2]])
			self.points=[[xmin,xmax,xmax,xmin,xmin,xmax,xmax,xmin],
						 [ymax,ymax,ymin,ymin,ymax,ymax,ymin,ymin],
						 [zmax,zmax,zmax,zmax,zmin,zmin,zmin,zmin]]
	def fix_temperature(self,T,multiplier=1.e10,file=None):
		''' Fixes temperatures at nodes within this zone. Temperatures fixed by adding an HFLX macro with high
			heat flow multiplier.
			
			:param T: Temperature to fix.
			:type T: fl64
			:param multiplier: Multiplier for HFLX macro (default = 1.e10)
			:type multiplier: fl64
			:param file: Name of auxiliary file to save macro.
			:type file: str
		'''
		if not self._parent: print 'fix_temperature() only available if zone associated with fdata() object'; return
		self._parent.add(fmacro('hflx',zone=self,param=(('heat_flow',T),('multiplier',multiplier)),file=file))
		self._fixedT = T
	def fix_pressure(self,P, T=30., impedance=1.e6, file = None):
		''' Fixes pressures at nodes within this zone. Pressures fixed by adding a FLOW macro with high
			impedance.
			
			:param P: Pressure to fix.
			:type P: fl64
			:param T: Temperature to fix (default = 30 degC).
			:type T: fl64
			:param impedance: Impedance for FLOW macro (default = 1.e6)
			:type impedance: fl64
			:param file: Name of auxiliary file to save macro.
			:type file: str
		'''
		if not self._parent: print 'fix_pressure() only available if zone associated with fdata() object'; return
		self._parent.add(fmacro('flow',zone=self,param=(('rate',P),('energy',-T),('impedance',impedance)),file=file))
		self._fixedP = [P,T]
	def copy_from(self,from_zone=None,grid_new=None,method = 'nearest',grid_old=None):
		'''Transfer zone information from one grid to another.
		
		:param from_zone: Zone object to convert.
		:type from_zone: fzone
		:param method: Method for node to node transfer of zone. Options are 'nearest', 'volume'.
		:type method: str
		
		'''
		if grid_new: self.grid = grid_new
		if grid_old: from_zone.grid = grid_old
		
		if not self.index: self.index = from_zone.index
		
		if not from_zone: print 'No zone supplied'; return
		if from_zone.type == 'rect': 		# if rectangular zone, copy across bounding box
			self.type = 'rect'
			self.points = from_zone.points
		else: 								# zone comprises a list of nodes
			if not from_zone.grid or not from_zone.nodelist: print 'Supplied zone does not contain grid information.'; return
			from_nodes = from_zone.nodelist
			if method == 'nearest':
				ndinds = np.unique([self.grid.node_nearest_point(nd.position) for nd in from_nodes])
				ndinds = [nd.index for nd in ndinds if nd != None]
			elif method == 'volume':
				'a'
			if not self.type: self.type = from_zone.type
			self.nodelist = [self.grid.node[ndind] for ndind in ndinds]			
	def plot(self,save='',angle=[45,45],color='k',connections=False,equal_axes=True,
			xlabel='x / m',ylabel='y / m',zlabel='z / m',title='',font_size='small'): 		#generates a 3-D plot of the zone.
		'''Generates and saves a 3-D plot of the zone.
		
		:param save: Name of saved zone image.
		:type save: str
		:param angle: 	View angle of zone. First number is azimuth angle in degrees, second number is tilt. Alternatively, if angle is 'x', 'y', 'z', view is aligned along the corresponding axis.
		:type angle: [fl64,fl64], str
		:param color: Colour of zone.
		:type color: str, [fl64,fl64,fl64]
		:param connections: Plot connections. If ``True`` all connections plotted. If between 0 and 1, random proportion plotted. If greater than 1, specified number plotted.
		:type connections: bool
		:param equal_axes: Force plotting with equal aspect ratios for all axes.
		:type equal_axes: bool
		
		:param xlabel: Label on x-axis.
		:type xlabel: str
		:param ylabel: Label on y-axis.
		:type ylabel: str
		:param zlabel: Label on z-axis.
		:type zlabel: str
		:param title: Title of plot.
		:type title: str
		
		:param font_size: Size of text on plot.
		:type font_size: str, int
		 
		*Example:*
		
		``zn.plot(save='myzone.png', angle = [45,45], xlabel = 'x / m', font_size = 'small', color = 'r')``
		 
		'''
		save = os_path(save)
		if isinstance(angle,str):
			if angle == 'x': angle = [0,0]
			elif angle == 'y': angle = [0,90]
			elif angle == 'z': angle = [90,90]
			else: return
		plotBoundingBox = False
		plotZoneBox = False
		if self._parent: plotBoundingBox = True	
		if self.type == 'rect': plotZoneBox = True
		# plot bounding box
		plt.clf()
		fig = plt.figure(figsize=[8.275,11.7])
		ax = plt.axes(projection='3d')
		ax.set_aspect('equal', 'datalim')
		
		ax.set_xlabel(xlabel,size=font_size)
		ax.set_ylabel(ylabel,size=font_size)
		ax.set_zlabel(zlabel,size=font_size)
		ax.set_title(title,size=font_size)
		
		for t in ax.get_xticklabels():
			t.set_fontsize(font_size)
		for t in ax.get_yticklabels():
			t.set_fontsize(font_size)
		for t in ax.get_zticklabels():
			t.set_fontsize(font_size)
		
		xmin,xmax = self._parent.grid.xmin, self._parent.grid.xmax
		ymin,ymax = self._parent.grid.ymin, self._parent.grid.ymax
		zmin,zmax = self._parent.grid.zmin, self._parent.grid.zmax
		
		if equal_axes:
			MAX = np.max([xmax-xmin,ymax-ymin,zmax-zmin])/2
			C = np.array([xmin+xmax,ymin+ymax,zmin+zmax])/2
			for direction in (-1, 1):
				for point in np.diag(direction * MAX * np.array([1,1,1])):
					ax.plot([point[0]+C[0]], [point[1]+C[1]], [point[2]+C[2]], 'w')
		ax.view_init(angle[0],angle[1])
		
		if plotBoundingBox:
				# x lines
			ax.plot([xmin,xmax],[ymin,ymin],[zmin,zmin],'k--')
			ax.plot([xmin,xmax],[ymax,ymax],[zmin,zmin],'k--')
			ax.plot([xmin,xmax],[ymax,ymax],[zmax,zmax],'k--')
			ax.plot([xmin,xmax],[ymin,ymin],[zmax,zmax],'k--')
				# y lines
			ax.plot([xmin,xmin],[ymin,ymax],[zmin,zmin],'k--')
			ax.plot([xmax,xmax],[ymin,ymax],[zmin,zmin],'k--')
			ax.plot([xmax,xmax],[ymin,ymax],[zmax,zmax],'k--')
			ax.plot([xmin,xmin],[ymin,ymax],[zmax,zmax],'k--')
				# z lines
			ax.plot([xmin,xmin],[ymin,ymin],[zmin,zmax],'k--')
			ax.plot([xmin,xmin],[ymax,ymax],[zmin,zmax],'k--')
			ax.plot([xmax,xmax],[ymax,ymax],[zmin,zmax],'k--')
			ax.plot([xmax,xmax],[ymin,ymin],[zmin,zmax],'k--')
		# plot node connections
		if connections:
			conns = []
			for node in self.nodelist:
				for nb in node.connected_nodes:
					if nb in self.nodelist:
						p1 = node.position
						p2 = nb.position
						conns.append((p1,p2))
			if not isinstance(connections,bool):		# plot all connections
				if connections>0 and connections<1: 	# plot proportion of connections
					connections = int(len(conns)*connections)
				connections = np.min([connections,len(conns)])
			import random
			random.shuffle(conns)
			conns = conns[:connections]
			for p1,p2 in conns:
				ax.plot([p1[0],p2[0]],[p1[1],p2[1]],[p1[2],p2[2]],color=color, linestyle = '-', linewidth = 0.5)								# plot some connections
		# plot nodes
		for node in self.nodelist: 
			ax.plot([node.position[0],],[node.position[1],],[node.position[2],],
			markerfacecolor=color,marker='o',markersize=3,markeredgecolor=color)		
		if plotZoneBox:
			xmax,xmin = np.max(self.points[0]),np.min(self.points[0])
			ymax,ymin = np.max(self.points[1]),np.min(self.points[1])
			zmax,zmin = np.max(self.points[2]),np.min(self.points[2])
				# x lines
			ax.plot([xmin,xmax],[ymin,ymin],[zmin,zmin],color=color,linestyle='-')
			ax.plot([xmin,xmax],[ymax,ymax],[zmin,zmin],color=color,linestyle='-')
			ax.plot([xmin,xmax],[ymax,ymax],[zmax,zmax],color=color,linestyle='-')
			ax.plot([xmin,xmax],[ymin,ymin],[zmax,zmax],color=color,linestyle='-')
				# y lines
			ax.plot([xmin,xmin],[ymin,ymax],[zmin,zmin],color=color,linestyle='-')
			ax.plot([xmax,xmax],[ymin,ymax],[zmin,zmin],color=color,linestyle='-')
			ax.plot([xmax,xmax],[ymin,ymax],[zmax,zmax],color=color,linestyle='-')
			ax.plot([xmin,xmin],[ymin,ymax],[zmax,zmax],color=color,linestyle='-')
				# z lines
			ax.plot([xmin,xmin],[ymin,ymin],[zmin,zmax],color=color,linestyle='-')
			ax.plot([xmin,xmin],[ymax,ymax],[zmin,zmax],color=color,linestyle='-')
			ax.plot([xmax,xmax],[ymax,ymax],[zmin,zmax],color=color,linestyle='-')
			ax.plot([xmax,xmax],[ymin,ymin],[zmin,zmax],color=color,linestyle='-')			
		
		extension, save_fname, pdf = save_name(save,variable='zone'+str(self.index),time=1)
		plt.savefig(save_fname, dpi=200, facecolor='w', edgecolor='w',orientation='portrait', 
		format=extension,transparent=True, bbox_inches=None, pad_inches=0.1)
		if pdf: 
			os.system('epstopdf ' + save_fname)
			os.remove(save_fname)			
	def topo(self,save='',cbar=True,equal_axes=True, method = 'nearest', divisions=[30,30], xlims=[],
			ylims=[], clims=[], levels=10,clabel='',
			xlabel='x / m',ylabel='y / m',zlabel='z / m',title='',font_size='small'): 		#generates a 2-D topographical plot of the zone.
		'''Returns a contour plot of the top surface of the zone.
		
		:param divisions: Resolution to supply mesh data.
		:type divisions: [int,int]
		:param method: Method of interpolation, options are 'nearest', 'linear'.
		:type method: str
		:param levels: Contour levels to plot. Can specify specific levels in list form, or a single integer indicating automatic assignment of levels. 
		:type levels: lst[fl64], int
		:param cbar: Add colour bar to plot.
		:param type: bool
		:param xlims: Plot limits on x-axis.
		:type xlims: [fl64, fl64]
		:param ylims: Plot limits on y-axis.
		:type ylims: [fl64, fl64]
		:param clims: Colour limits. 
		:type clims: [fl64,fl64]
		:param save: Name to save plot. Format specified extension (default .png if none give). Supported extensions: .png, .eps, .pdf.
		:type save: str
		:param xlabel: Label on x-axis.
		:type xlabel: str
		:param ylabel: Label on y-axis.
		:type ylabel: str
		:param title: Plot title.
		:type title: str
		:param font_size: Specify text size, either as an integer or string, e.g., 10, 'small', 'x-large'.
		:type font_size: str, int
		:param equal_axes: Specify equal scales on axes.
		:type equal_axes: bool
		
		*Example:*
		
		``dat.zone[2].topo('zoneDEMtopo.png',method = 'linear')``
		
		'''	
		save = os_path(save)
		if not self.nodelist: print 'No node information, aborting...'; return
		if not title: 
			title = 'Topographic plot of zone ' +str(self.index)
			if self.name: title += ': '+self.name
		# assemble data
		xs = np.unique([nd.position[0] for nd in self.nodelist])
		ys = np.unique([nd.position[1] for nd in self.nodelist])
		xmin = np.min(xs); xmax = np.max(xs)
		ymin = np.min(ys); ymax = np.max(ys)		
		xrange = np.linspace(xmin,xmax,divisions[0])
		yrange = np.linspace(ymin,ymax,divisions[1])
		XI,YI = np.meshgrid(xs,ys)
		X,Y = np.meshgrid(xrange,yrange)
		
		ZI = np.ones((len(ys),len(xs)))*self._parent.grid.zmin-1
		#print XI.shape,ZI.shape
		for nd in self.nodelist:
			i = np.where(xs==nd.position[0])[0][0]
			j = np.where(ys==nd.position[1])[0][0]
			ZI[j,i] = np.max([ZI[j,i],nd.position[2]])
		
		pts = np.transpose(np.reshape((X,Y),(2,X.size)))
		ptsI = np.transpose(np.reshape((XI,YI,ZI),(3,XI.size)))
		
		from scipy.interpolate import griddata
		vals = griddata(ptsI[:,:2],ptsI[:,2],pts,method=method)
		vals =  np.reshape(vals,(X.shape[0],X.shape[1]))
		
		# plot topo
		plt.clf()
		fig = plt.figure(figsize=[8.275,11.7])
		ax = plt.axes([0.15,0.15,0.7,0.7])
		if xlims: ax.set_xlim(xlims)
		if ylims: ax.set_ylim(ylims)
		if equal_axes: ax.set_aspect('equal', 'datalim')
		CS = plt.contourf(X,Y,vals,levels)
		if clims: CS.vmin=clims[0]; CS.vmax=clims[1]
		if xlabel: plt.xlabel(xlabel,size=font_size)		
		if ylabel: plt.ylabel(ylabel,size=font_size)
		if title: plt.title(title,size=font_size)
		if cbar:			
			cbar=plt.colorbar(CS)
			for t in cbar.ax.get_yticklabels():
				t.set_fontsize(font_size)
		for t in ax.get_xticklabels():
			t.set_fontsize(font_size)
		for t in ax.get_yticklabels():
			t.set_fontsize(font_size)
					
		ax.set_aspect('equal', 'datalim')
		extension, save_fname, pdf = save_name(save,variable='zone_topo'+str(self.index),time=1)
		plt.savefig(save_fname, dpi=200, facecolor='w', edgecolor='w',orientation='portrait', 
		format=extension,transparent=True, bbox_inches=None, pad_inches=0.1)
	def _get_info(self):
		"""Print details of the zone to the screen."""
		ws = 'Zone '+str(self.index)+'\n'
		ws+='\nGeometric properties.......\n'
		if self.type == 'rect':
			ws +=  '  Type: rectangular box\n'
			if self.nodelist: ws += '  Contains '+str(len(self.nodelist))+' nodes\n'
			pts = np.array(self.points)
			if np.size(pts)==24: pts=pts.reshape(3,8)
			else: pts = pts.reshape(2,4)			
			xmin, xmax = np.min(pts[0,:]), np.max(pts[0,:])
			ymin, ymax = np.min(pts[1,:]), np.max(pts[1,:])
			zmin, zmax = np.min(pts[2,:]), np.max(pts[2,:])
			dx,dy,dz = [xmax-xmin,ymax-ymin,zmax-zmin]
			ws += '  dimensions: ['+str(dx)+', '+str(dy)+', '+str(dz)+']'
			if 100*dz<dx and 100*dz<dy: ws += '  (plane at z = '+str((zmin+zmax)/2)+')'
			elif 100*dx<dy and 100*dx<dz: ws += '  (plane at x = '+str((xmin+xmax)/2)+')'
			elif 100*dy<dz and 100*dy<dz: ws += '  (plane at y = '+str((ymin+ymax)/2)+')'
			elif 100*dz<dx and 100*dy<dx: ws += '  (column at x = '+str((xmin+xmax)/2)+')'
			elif 100*dx<dy and 100*dz<dy: ws += '  (column at y = '+str((ymin+ymax)/2)+')'
			elif 100*dx<dz and 100*dy<dz: ws += '  (column at z = '+str((zmin+zmax)/2)+')'
			ws += '\n'
			ws += '  x-range: '+str(xmin)+' - '+str(xmax)+'\n'
			ws += '  y-range: '+str(ymin)+' - '+str(ymax)+'\n'
			ws += '  z-range: '+str(zmin)+' - '+str(zmax)+'\n'
			ws += '  mid-point: ['+str((xmin+xmax)/2.)+', '+str((ymin+ymax)/2.)+', '+str((zmin+zmax)/2.)+']\n'
			
			#print ws; return
		elif self.type == 'list':
			#ws = 'Zone '+str(self.index)+'\n'
			#ws+='\nGeometric properties.......\n'
			ws +=  '  Type: list\n'
			ws += '  Contains '+str(len(self.nodelist))+' nodes\n'
			pts=np.array(self.points)
			ws += '  x-range: '+str(np.min(pts[:,0]))+' - '+str(np.max(pts[:,0]))+'\n'
			ws += '  y-range: '+str(np.min(pts[:,1]))+' - '+str(np.max(pts[:,1]))+'\n'
			ws += '  z-range: '+str(np.min(pts[:,2]))+' - '+str(np.max(pts[:,2]))+'\n'
			ws += '  mid-point: ['+str(np.mean(pts[:,0]))+', '+str(np.mean(pts[:,1]))+', '+str(np.mean(pts[:,2]))+']\n'
			if pts.shape[0]<20:
				ws+='  points: ['+str(self.points[0][0])+', '+str(self.points[0][1])+', '+str(self.points[0][2])+']\n'			
				for pt in self.points[1:]:
					ws+='        ['+str(pt[0])+', '+str(pt[1])+', '+str(pt[2])+']\n'			
			#print ws; return
		elif self.type == 'nnum':
			ws += '  Type: nnum (list of nodes)\n'
			ws += '  Contains '+str(len(self.nodelist))+' nodes\n'
		elif not self.index:
			ws += '  Background zone (denoted 1 0 0), encompassing all nodes.\n'
		else: return
		
		ws += '\nMaterial properties........\n'
		if self._permeability != None: ws += '  permeability...... '+str(self._permeability)+'\n'
		if self._conductivity != None: ws += '  conductivity...... '+str(self._conductivity)+'\n'
		if self._density: ws += '  density........... '+str(self._density)+'\n'
		if self._specific_heat: ws += '  specific heat..... '+str(self._specific_heat)+'\n'
		if self._porosity: ws += '  porosity.......... '+str(self._porosity)+'\n'
		if self._youngs_modulus: ws += '  Youngs modulus.... '+str(self._youngs_modulus)+'\n'
		if self._poissons_ratio: ws += '  Poissons ratio.... '+str(self._poissons_ratio)+'\n'
		if self._thermal_expansion: ws += '  thermal expansion. '+str(self._thermal_expansion)+'\n'
		if self._pressure_coupling: ws += '  pressure coupling. '+str(self._pressure_coupling)+'\n'
		
		ws += '\nInitial conditions.........\n'
		if self._Pi: ws += '  pressure.......... '+str(self._Pi)+'\n'
		if self._Ti: ws += '  temperature....... '+str(self._Ti)+'\n'
		if self._Si: ws += '  saturation........ '+str(self._Si)+'\n'
		
		ws += '\nBoundary conditions........\n'
		if self._fixedT: ws += '  fixed temperature.... '+str(self._fixedT)+'\n'
		if self._fixedP: 
			ws += '  fixed pressure....... '+str(self._fixedP[0])+'\n'
			ws += '    inflow temperature. '+str(self._fixedP[1])+'\n'
		
		print ws
	what = property(_get_info) 				#: Print to screen information about the zone.
	def _get_nodes(self):
		"""Assemble a list of fnode objects contained in the zone."""
		nds  = []
		if self.type == 'rect':
			if not self._parent.grid: self._nodelist = nds; return self._nodelist
			xmax,xmin = np.max(self.points[0]),np.min(self.points[0])
			ymax,ymin = np.max(self.points[1]),np.min(self.points[1])
			if self._parent.grid.dimensions == 3:
				zmax,zmin = np.max(self.points[2]),np.min(self.points[2])
			else:
				zmax,zmin = self._parent.grid.zmax+.01,self._parent.grid.zmin-.01
			for nd in self._parent.grid.nodelist:
				x,y,z = nd.position
				if (x<=xmax) and (x>=xmin) and (y<=ymax) and (y>=ymin) and (z<=zmax) and (z>=zmin):
					nds.append(nd)
			self._nodelist = nds
		if self.index == 0: self._nodelist = self._parent.grid.nodelist
		return self._nodelist
	def _set_nodes(self,value):
		if self.type == 'rect': print 'Error: nodelist for zone defined by content of points.'; return
		self._nodelist = value
	nodelist = property(_get_nodes,_set_nodes)	#: (*lst[fnode]*) List of nodes contained within the zone.
	def _get_node(self): return dict([(nd.index,nd) for nd in self.nodelist])
	node = property(_get_node) #: (*dict[fnode]*) Dictionary of nodes contained within the zone, indexed by node number.
	def _get_points(self): 
		"""Assemble spatial data as it would appear in an FEHM input file."""
		pts=[]
		if self.type in ['nnum','list']:
			if not self._parent.grid: self._points = pts; return self._points
			row = []
			if self.type == 'nnum': row.append(len(self.nodelist))
			for nd in self.nodelist:
				if self.type == 'list': pts.append(nd.position)
				elif self.type == 'nnum': row.append(nd.index)
				if len(row) == 10: pts.append(row); row = []
			if row != []: pts.append(row)
			self._points = pts
		return self._points		
	def _set_points(self,value): 
		if self.type in ['list','nnum']: print 'Error: points defined by content of nodelist.'; return
		self._points = value
	points = property(_get_points,_set_points)#: (*lst[fl64]*) Spatial data defining the zone.
	def _get_permeability(self): return self._permeability
	def _set_permeability(self,value): 
		self._permeability = value
		# set commands
		if not self._parent: print 'Zone not associated with input file, no macro changes made.'; return
		if isinstance(value,(int,float)): kx = value; ky = value; kz = value
		elif isinstance(value,(list,tuple,np.ndarray)) and len(value)==3: kx,ky,kz = value
		if self.index in self._parent.perm.keys():
			if self._updateFlag:
				self._parent.perm[self.index].param['kx']=kx
				self._parent.perm[self.index].param['ky']=ky
				self._parent.perm[self.index].param['kz']=kz
			#self._parent._associate_macro(self._parent.perm[self.index])
		else:
			self._parent.add(fmacro('perm',zone=self.index,param=(('kx',kx),('ky',ky),('kz',kz))))
		if self._parent:
			for nd in self.nodelist:
				if not (nd.permeability is not None and self.index == 0): 
					nd._permeability = np.array([kx,ky,kz])
	permeability = property(_get_permeability, _set_permeability) #: (*fl64*,*lst*) Permeability properties of zone.
	def _get_conductivity(self): return self._conductivity
	def _set_conductivity(self,value): 
		self._conductivity = value
		# set commands
		if not self._parent: print 'Zone not associated with input file, no macro changes made.'; return
		if isinstance(value,(int,float)): kx = value; ky = value; kz = value
		elif isinstance(value,(list,tuple,np.ndarray)) and len(value)==3: kx,ky,kz = value
		if self.index in self._parent.cond.keys():
			if self._updateFlag:
				self._parent.cond[self.index].param['cond_x']=kx
				self._parent.cond[self.index].param['cond_y']=ky
				self._parent.cond[self.index].param['cond_z']=kz
			#self._parent._associate_macro(self._parent.cond[self.index])
		else:
			self._parent.add(fmacro('cond',zone=self.index,param=(('cond_x',kx),('cond_y',ky),('cond_z',kz))))
		if self._parent:
			for nd in self.nodelist:
				if not (nd.conductivity is not None and self.index == 0): 
					nd._conductivity = np.array([kx,ky,kz])
	conductivity = property(_get_conductivity, _set_conductivity) #: (*fl64*,*lst*) Conductivity properties of zone.
	def _get_density(self): return self._density
	def _set_density(self,value): 
		self._density = value
		# set commands
		if not self._parent: print 'Zone not associated with input file, no macro changes made.'; return
		if self.index in self._parent.rock.keys():
			if self._updateFlag:
				self._parent.rock[self.index].param['density']=value
			#self._parent._associate_macro(self._parent.rock[self.index])
		else:
			self._parent.add(fmacro('rock',zone=self.index,param=(('density',value),('specific_heat',dflt.specific_heat),('porosity',dflt.porosity))))
			print 'WARNING: Assigning default specific heat and porosity...'
			self.specific_heat = dflt.specific_heat
			self.porosity = dflt.porosity
		if self._parent:
			for nd in self.nodelist:
				if not (nd.density is not None and self.index == 0): 
					nd._density = value
	density = property(_get_density, _set_density) #: (*fl64*) 	Density of zone.
	def _get_specific_heat(self): return self._specific_heat
	def _set_specific_heat(self,value): 
		self._specific_heat = value
		# set commands
		if not self._parent: print 'Zone not associated with input file, no macro changes made.'; return
		if self.index in self._parent.rock.keys():
			if self._updateFlag:
				self._parent.rock[self.index].param['specific_heat']=value			
			#self._parent._associate_macro(self._parent.rock[self.index])
		else:
			self._parent.add(fmacro('rock',zone=self.index,param=(('density',dflt.density),('specific_heat',value),('porosity',dflt.porosity))))
			print 'WARNING: Assigning default density and porosity...'
			self.density = dflt.density
			self.porosity = dflt.porosity
		if self._parent:
			for nd in self.nodelist:
				if not (nd.specific_heat is not None and self.index == 0): 
					nd._specific_heat = value
	specific_heat = property(_get_specific_heat, _set_specific_heat) #: (*fl64*) Specific heat of zone.
	def _get_porosity(self): return self._porosity
	def _set_porosity(self,value): 
		self._porosity = value
		# set commands
		if not self._parent: print 'Zone not associated with input file, no macro changes made.'; return
		if self.index in self._parent.rock.keys():
			if self._updateFlag:
				self._parent.rock[self.index].param['porosity']=value
			#self._parent._associate_macro(self._parent.rock[self.index])
		else:
			self._parent.add(fmacro('rock',zone=self.index,param=(('density',dflt.density),('specific_heat',dflt.specific_heat),('porosity',value))))
			print 'WARNING: Assigning default density and specific heat...'
			self.specific_heat = dflt.specific_heat
			self.density = dflt.density
		if self._parent:
			for nd in self.nodelist:
				if not (nd.porosity is not None and self.index == 0): 
					nd._porosity = value
	porosity = property(_get_porosity, _set_porosity) #: (*fl64*) Porosity of zone.
	def _get_youngs_modulus(self): return self._youngs_modulus
	def _set_youngs_modulus(self,value): 
		self._youngs_modulus = value
		# set commands
		if not self._parent: print 'Zone not associated with input file, no macro changes made.'; return
		if self.index in self._parent.elastic.keys():
			if self._updateFlag:
				self._parent.elastic[self.index].param['youngs_modulus']=value
			#self._parent._associate_macro(self._parent.elastic[self.index])
		else:
			self._parent.add(fmacro('elastic',zone=self.index,param=(('youngs_modulus',value),('poissons_ratio',dflt.poissons_ratio))))
			print 'WARNING: Assigning default Poissons ratio...'
			self.poissons_ratio = dflt.poissons_ratio
		if self._parent:
			for nd in self.nodelist:
				if not (nd.youngs_modulus is not None and self.index == 0): 
					nd._youngs_modulus = value
	youngs_modulus = property(_get_youngs_modulus, _set_youngs_modulus) #: (*fl64*) Young's modulus of zone.
	def _get_poissons_ratio(self): return self._poissons_ratio
	def _set_poissons_ratio(self,value): 
		self._poissons_ratio = value
		# set commands
		if not self._parent: print 'Zone not associated with input file, no macro changes made.'; return
		if self.index in self._parent.elastic.keys():
			if self._updateFlag:
				self._parent.elastic[self.index].param['poissons_ratio']=value
			#self._parent._associate_macro(self._parent.elastic[self.index])
		else:
			self._parent.add(fmacro('elastic',zone=self.index,param=(('youngs_modulus',dflt.youngs_modulus),('poissons_ratio',value))))
			print 'WARNING: Assigning default Youngs modulus...'
			self.youngs_modulus = dflt.youngs_modulus
		if self._parent:
			for nd in self.nodelist:
				if not (nd.poissons_ratio is not None and self.index == 0): 
					nd._poissons_ratio = value
	poissons_ratio = property(_get_poissons_ratio, _set_poissons_ratio) #: (*fl64*) Poisson's ratio of zone.
	def _get_thermal_expansion(self): return self._thermal_expansion
	def _set_thermal_expansion(self,value): 
		self._thermal_expansion = value
		# set commands
		if not self._parent: print 'Zone not associated with input file, no macro changes made.'; return
		if self.index in self._parent.biot.keys():
			if self._updateFlag:
				self._parent.biot[self.index].param['thermal_expansion']=value
			#self._parent._associate_macro(self._parent.biot[self.index])
		else:
			self._parent.add(fmacro('biot',zone=self.index,param=(('thermal_expansion',value),('pressure_coupling',dflt.pressure_coupling))))
			print 'WARNING: Assigning default pressure coupling...'
			self.pressure_coupling = dflt.pressure_coupling
		if self._parent:
			for nd in self.nodelist:
				if not (nd.thermal_expansion is not None and self.index == 0): 
					nd._thermal_expansion = value
	thermal_expansion = property(_get_thermal_expansion, _set_thermal_expansion) #: (*fl64*) Coefficient of thermal expansion of zone.
	def _get_pressure_coupling(self): return self._pressure_coupling
	def _set_pressure_coupling(self,value): 
		self._pressure_coupling = value
		# set commands
		if not self._parent: print 'Zone not associated with input file, no macro changes made.'; return
		if self.index in self._parent.biot.keys():
			if self._updateFlag:
				self._parent.biot[self.index].param['pressure_coupling']=value
			#self._parent._associate_macro(self._parent.biot[self.index])
		else:
			self._parent.add(fmacro('biot',zone=self.index,param=(('thermal_expansion',dflt.thermal_expansion),('pressure_coupling',value))))
			print 'WARNING: Assigning default thermal expansion...'
			self.thermal_expansion = dflt.thermal_expansion
		if self._parent:
			for nd in self.nodelist:
				if not (nd.pressure_coupling is not None and self.index == 0): 
					nd._pressure_coupling = value
	pressure_coupling = property(_get_pressure_coupling, _set_pressure_coupling) #: (*fl64*) Pressure coupling term of zone.
	def _get_Pi(self): return self._Pi
	def _set_Pi(self,value): 
		self._Pi = value
		# set commands
		if not self._parent: print 'Zone not associated with input file, no macro changes made.'; return
		if self.index in self._parent.pres.keys():
			if self._updateFlag:
				self._parent.pres[self.index].param['pressure']=value
			#self._parent._associate_macro(self._parent.pres[self.index])
		else:
			self._parent.add(fmacro('pres',zone=self.index,param=(('pressure',value),('temperature',dflt.Ti),('saturation',1))))
			print 'WARNING: Assigning default initial temperature (fully saturated liquid)...'
			self.Ti = dflt.Ti
		if self.Ti > tsat(self.Pi)[0]: 
			self._parent.pres[self.index].param['saturation']=3
			self.Si = 0.
		else: 
			self._parent.pres[self.index].param['saturation']=1
			self.Si = 1.
		if self._parent:
			for nd in self.nodelist:
				if not (nd.Pi is not None and self.index == 0): 
					nd._Pi = value
	Pi = property(_get_Pi, _set_Pi) #: (*fl64*) Initial pressure in zone.
	def _get_Ti(self): return self._Ti
	def _set_Ti(self,value): 
		self._Ti = value
		# set commands
		if not self._parent: print 'Zone not associated with input file, no macro changes made.'; return
		if self.index in self._parent.pres.keys():
			if self._updateFlag:
				self._parent.pres[self.index].param['temperature']=value
			#self._parent._associate_macro(self._parent.pres[self.index])
		else:
			self._parent.add(fmacro('pres',zone=self.index,param=(('pressure',dflt.Pi),('temperature',value),('saturation',1))))
			print 'WARNING: Assigning default initial pressure (fully saturated liquid)...'
			self._Pi = dflt.Pi
		if self._Ti > tsat(self._Pi)[0]: 
			self._parent.pres[self.index].param['saturation']=3
			self._Si = 0.
		else: 
			self._parent.pres[self.index].param['saturation']=1
			self._Si = 1.
		if self._parent:
			for nd in self.nodelist:
				if not (nd.Ti is not None and self.index == 0): 
					nd._Ti = value
	Ti = property(_get_Ti, _set_Ti) #: (*fl64*) Initial temperature in zone.
	def _get_Si(self): return self._Si
	def _set_Si(self,value): 
		self._Si = value
		# set commands
		if not self._parent: print 'Zone not associated with input file, no macro changes made.'; return
		if self.index in self._parent.pres.keys():
			if self._updateFlag:
				self._parent.pres[self.index].param['temperature']=value
				self._parent.pres[self.index].param['saturation']=2
			#self._parent._associate_macro(self._parent.pres[self.index])
		else:
			self._parent.add(fmacro('pres',zone=self.index,param=(('pressure',dflt.pressure),('temperature',value),('saturation',2))))
			print 'WARNING: Assigning default initial pressure (two phase)...'
		self._Ti = tsat(self._parent.pres[self.index].param['pressure'])[0]
		if self._parent:
			for nd in self.nodelist:
				if not (nd.Si is not None and self.index == 0): 
					nd._Si = value
	Si = property(_get_Si, _set_Si) #: (*fl64*) Initial saturation in zone.
	def _check(self):
		# if file called for but non-existant on disk, print warning
		if self.type == None: print 'WARNING: Zone '+str(self.index)+' type not assigned.'
		if self.points == None: print 'WARNING: Zone '+str(self.index)+' points array is empty.'
class fmacro(object): 						#FEHM macro object
	"""FEHM macro object.
	
	"""
	__slots__=['_type','_param','_parent','_zone','_subtype','_file','_write_one_macro']
	def __init__(self,type='',zone=[],param=[],subtype='',file = None,write_one_macro=False):
		self._type = type 		
		if type == 'stressboun' and not subtype: subtype = 'fixed'
		self._param = None 		
		self._check_type()
		self._assign_param()
		self._parent = None
		if param: self._set_param2(param)	
		self._zone = []			
		if zone != []: self.zone = zone
		self._subtype = subtype	
		self._check_zone()
		self._file = file
		self._write_one_macro = write_one_macro
	def _assign_param(self): 
		'''Assign parameters if supplied on initialisation.'''
		self._param = dict(macro_list[self.type])
		if self.type not in ['stressboun']:self._param = ImmutableDict(self._param)
	def _set_param2(self,param):
		'''Assign keys in param attribute appropriate to specific macro.'''
		for par,key in zip(param,macro_list[self.type]):
			if isinstance(par,list) or isinstance(par,tuple):
				self._param[par[0]] = par[1]
			else:
				self._param[key[0]] = par
	def _check_type(self):
		'''Determine if macro is supported.'''
		if self.type not in macro_list.keys(): return None
	def _check_zone(self):
		'''Determine if zone definitions are acceptable.'''
		if not self.zone: return
		elif isinstance(self.zone,fzone): return
		elif isinstance(self.zone,tuple):
			if len(self.zone) != 3: self.zone=None; return
			self.zone = tuple([int(pt) for pt in self.zone])
		elif isinstance(self.zone,list):
			newlist = []
			for zn in self.zone:
				if isinstance(zn,fzone) or (isinstance(zn,tuple) and len(zn) == 3): newlist.append(zn)
			self.zone = newlist
		elif isinstance(self.zone,int) or isinstance(self.zone,str): return
		else: self.zone=None; return
	def __repr__(self): 
		prntStr = self.type +': '
		if isinstance(self.zone,fzone): prntStr += str(self.zone.index)
		elif isinstance(self.zone,list): 
			for zn in self.zone: prntStr += str(self.zone.index)+ ' ,'
			prntStr = prntStr[:-2]
		elif isinstance(self.zone,tuple):
			zn = self.zone
			prntStr += '('+str(zn[0]) +', '	+str(zn[1]) +', '+str(zn[2]) +')'
		return prntStr
	def _get_type(self): return self._type
	def _set_type(self,type): 
		oldtype = self._type
		self._type = type
		if oldtype != type: self.param = ImmutableDict(dict(macro_list[self._type]))
	type = property(_get_type,_set_type)#: (*str*) Name of the macro. Macro names are identical to those invoked in FEHM.
	def _get_param(self): return self._param
	def _set_param(self,value): self._param = value
	param = property(_get_param, _set_param) #: (*dict[fl64]*) A dictionary of values defining the operation of the macro. See table below for macro-specific dictionary keys.
	def _get_zone(self): return self._zone
	def _set_zone(self,value): self._zone = value
	zone = property(_get_zone,_set_zone)#: (*fzone, lst[fzone], tuple[int,int,int], zone key*) The zone, zones or nodes to which the macro is assigned. Note, only permmodel and rlp can be assigned lists of zones. Optionally, a key (index or string) may be passed, in which case the zone will be retrieved when the macro is added to the model.
	def _get_subtype(self): return self._subtype
	def _set_subtype(self,value):
		self._subtype = value
		if self.type != 'stressboun': print 'WARNING: subtype ignored for non-stressboun macros'
	subtype = property(_get_subtype,_set_subtype)	#: (*str*) Macro subtype, required for **STRESSBOUN** macro.
	def _get_file(self): return self._file
	def _set_file(self,value): self._file = value
	file = property(_get_file,_set_file)#: (*str*) File string where information about the macro is stored. If file does not currently exist, it will be created and written to when the FEHM input file is written.
	def _check(self):
		# if not zone assigned, apply default background
		if self._zone == None: 
			prntStr = 'WARNING: Macro '+str(self.type)+' has no zone assigned.'
		# if parameter value not assigned, print warning
		for key in self.param.keys():
			if self.param[key] == None: print 'WARNING: Macro '+str(self.type)+':'+str(self.zone.index)+' '+key+' not assigned.'
	def _get_info(self):
		prntStr = self.type + ': ' + macro_descriptor[self.type] +'\n'
		# print zone info
		zns = self.zone
		if isinstance(zns,fzone):
			prntStr += 'Assigned to zone ' +str(zns.index)+'.\n'
		elif isinstance(zns,list):
			prntStr += 'Assigned to zones '
			for zn in zns: 
				if isinstance(zn,fzone):
					prntStr += str(zn.index) +', '
				elif isinstance(zn,tuple):
					prntStr += '('+str(zn[0]) +', '	+str(zn[1]) +', '+str(zn[2]) +'), '
			prntStr = prntStr[:-2]+'.\n'
		elif isinstance(zns,tuple):
			prntStr += 'Assigned to node set ('+str(zns[0]) +', '	+str(zns[1]) +', '+str(zns[2]) +').\n'
		# print parameter info
		prntStr += 'Parameters: \n'
		for par in macro_list[self.type]:
			if self.param[par[0]] is None:
				prntStr += '    ' + par[0] + ': Not assigned\n'
			else:
				prntStr += '    ' + par[0] + ': ' + str(self.param[par[0]]) + '\n'
		if self.type == 'stressboun': prntStr += self._more_info_stressboun()
		if self.type == 'flow': prntStr += self._more_info_flow()
		print prntStr + '\n'
	what = property(_get_info)		#: Return a summary of the macros function.
	def _more_info_flow(self):
		'''Return additional information about flow macro.'''
		prntStr = ''
		if self.param['rate']>0:	
			if self.param['energy']>0:
				if self.param['impedance']==0: prntStr += 'Mass production at fixed rate of ' + str(abs(self.param['rate']))+' kg/s'
				else: prntStr += 'Mass production against specified WHP of ' + str(abs(self.param['rate'])) + ' MPa'
		else:
			if self.param['energy']>0:
				if self.param['impedance']==0: prntStr += 'Mass injection of '+str(self.param['energy'])+' MJ/kg fluid at fixed rate of ' + str(abs(self.param['rate']))+' kg/s'
				else:prntStr += 'Mass injection of '+str(self.param['energy'])+' MJ/kg fluid against specified WHP of ' + str(abs(self.param['rate']))+' MPa'
			else:
				if self.param['impedance']==0: prntStr += 'Mass injection of '+str(abs(self.param['energy']))+' degC fluid at fixed rate of ' + str(abs(self.param['rate']))+' kg/s'
				else:prntStr += 'Mass injection of '+str(abs(self.param['energy']))+' degC fluid against specified WHP of ' + str(abs(self.param['rate']))+' MPa'
		return prntStr
	def _more_info_stressboun(self):
		'''Return additional information about stressboun macro.'''
		prntStr = ''
		strsDirs = dict([(1,'x-dir'),(2,'y-dir'),(3,'z-dir')])
		if self.subtype=='lithograd': 
			prntStr += 'lithograd, '
			prntStr += strsDirs[abs(self.param['direction'])]+', '
			prntStr += 'stress grad = ' + str(self.param['value']) + ' MPa/m'
		elif self.subtype == 'distributed':
			prntStr += self.subtype +' force, '	
			prntStr += strsDirs[abs(self.param['direction'])]+', '
			prntStr += str(self.param['value'])+ ' MPa'
		elif self.subtype == 'lithostatic':
			prntStr +='not done!'
		else:
			if self.param['direction']>0: prntStr += 'fixed disp, '
			else: prntStr += 'fixed force, '
			prntStr += strsDirs[abs(self.param['direction'])]+', '
			prntStr += str(self.param['value'])+' '
			if self.param['direction']>0: prntStr += 'm'
			else: prntStr += 'MPa'
		return prntStr
class fmodel(object): 						#FEHM model object.
	'''Model object, used in a variety of macro definitions.
	
	Model objects should have:
		- a type for the macro
		- a list of zones to which the model is assigned.
		- an index for the specific model.
		- a dictionary of parameters for the model.	
	'''
	slots = ['_type','_param','_index','_parent','_zonelist','_zone','_file']
	def __init__(self,type='',zonelist=[],param=[],index = None,file = None):
		self._type = type 		
		self._param = None 		
		self._check_type()
		self._index = None	
		if index: self._index = index
		self._assign_param()
		self._parent = None
		# check param hasn't been misspecified
		if len(param) ==2:
			if not isinstance(param[0],tuple): param = (param,)
		if param: self._set_param2(param)	
		self._zonelist = []			
		if zonelist != []: self.zonelist = zonelist
		self._zone = {}
		self._check_zone()
		self._file = file
	def _check_type(self):
		'''Determine if macro is supported.'''
		if self.type not in model_list.keys(): return None
	def _assign_param(self): 
		'''Assign parameters if supplied on initialisation.'''
		if self.index in model_list[self.type].keys():
			self._param = dict([(par,None) for par in model_list[self.type][self.index]])
			self._param = ImmutableDict(self._param)
		else: 
			self._param = {}
	def _set_param2(self,param):
		'''Assign keys in param attribute appropriate to specific macro.'''
		if self.index not in model_list[self.type].keys():	
			self._param = dict([('param'+str(i+1),par[1]) for i,par in enumerate(param)])
			self._param = ImmutableDict(self._param)		
			return																		
		#elif len(param) != len(self._param.keys()): 									
		elif param.__len__() != len(self._param.keys()): 
			print param
			print param.__len__(), len(self._param.keys()) 	
			return		# return if numbers don't match up
		
		if self.index in model_list[self.type].keys():
			paramDict = model_list[self.type][self.index]
		else:
			paramDict = ['param'+str(i+1) for i in range(len(self._param.keys()))]
		for par,key in zip(param,paramDict):
			if isinstance(par,list) or isinstance(par,tuple):
				self._param[par[0]] = par[1]
			else:
				self._param[key] = par		
	def _check_zone(self):
		'''Determine if zone definitions are acceptable.'''
		if not self.zonelist: return
		elif isinstance(self.zonelist,(fzone,int,str)): self.zonelist = [self.zonelist]
		elif isinstance(self.zonelist,tuple):
			if len(self.zonelist) != 3: self.zonelist=None; return
			self.zonelist = [tuple([int(pt) for pt in self.zonelist])]
		elif isinstance(self.zonelist,list):
			newlist = []
			for zn in self.zonelist:
				if isinstance(zn,(fzone,int,str)) or (isinstance(zn,tuple) and len(zn) == 3): newlist.append(zn)
			self.zonelist = newlist
		else: self.zonelist=None; return
		if self._parent:
			newlist = []
			for zn in self.zonelist:
				if zn in self._parent.zone.keys():
					newlist.append(self._parent.zone[zn])
			self.zonelist = newlist
	def _get_type(self): return self._type
	def _set_type(self,value): 
		oldtype = self._type
		self._type = type
		if oldtype != type: 
			param_dicts = model_list[self._type]
			if self.index not in param_dicts:
				print 'ERROR: model index not known.'
				return
			self.param = ImmutableDict(param_dicts[self.index])
	type = property(_get_type, _set_type) #: (*str*) Name of the macro for this model. Macro names are identical to those invoked in FEHM.
	def _get_param(self): return self._param
	def _set_param(self,value): self._param = value
	param = property(_get_param, _set_param) #: (*dict[fl64]*) A dictionary of values defining the operation of the macro. See table below for macro-specific dictionary keys.
	def _get_index(self): return self._index
	def _set_index(self,value): self._index = value
	index = property(_get_index, _set_index) #: (*int*) Index of the model to be invoked.
	def _get_zonelist(self): return self._zonelist
	def _set_zonelist(self,value): self._zonelist = value
	zonelist = property(_get_zonelist, _set_zonelist) #: (*list*) A list of zones to which the model is applied.
	def _get_zone(self): 
		tempdict = []
		for zn in self.zonelist:
			if isinstance(zn,tuple):
				tempdict.append([tuple,tuple])
			elif isinstance(zn,fzone):
				tempdict.append([zn.index,zn])
		return dict(tempdict)
	zone = property(_get_zone) #: (**)
	def _get_file(self): return self._file
	def _set_file(self,value): self._file = value
	file = property(_get_file, _set_file) #: (**)
class fincon(object): 						#FEHM restart object.
	'''Initial conditions object. Also called a restart file.
	
	Reading one of these files associates the temperature, pressure, saturation etc. data with grid nodes
	and sets up fehmn.files to use the file for restarting.
	'''
	def __init__(self,inconfilename=''):
		self._source = ''
		self._parent = None
		self._time = None
		self._changeTime = False
		self._writeOut = False 		# flag that changes have been made and the incon file should be rewritten
		self._stressgradCalled = False
		self._T = []
		self._P = []
		self._S = []
		self._co2aq = []
		self._eos = []
		self._co2_eos = []
		self._dc_eos = []
		self._S_co2l = []
		self._strs_xx = []
		self._strs_yy = []
		self._strs_zz = []
		self._strs_xy = []
		self._strs_yz = []
		self._strs_xz = []
		self._disp_x = []
		self._disp_y = []
		self._disp_z = []
		self._path = fpath(parent=self)
		
		if inconfilename: self._path.filename = inconfilename
		if self.filename: self.read()
	def read(self,inconfilename='',if_new = False):
		'''Parse a restart file for variable information.
		
		:param inconfilename: Name of restart file.
		:type inconfilename: str
		'''
		
		if inconfilename: self._path.filename = inconfilename
		
		if if_new and not os.path.isfile(self._path.full_path): return False
		
		infile = open(self._path.full_path,'r')	
		
		self._parent.files.incon = inconfilename

		lns = infile.readlines()
		infile.close()
		# check if incon file finished writing
		if not (lns[-1].startswith('no fluxes') or lns[-2].startswith('no fluxes') or lns[-3].startswith('no fluxes')):
			return
		cnt = 0
		ln = lns[cnt].strip(); cnt +=1
		ln = lns[cnt].strip(); cnt +=1
		self._source = ln
		ln = lns[cnt].strip(); cnt +=1
		new_time = float(ln)
		if (new_time == self.time) and if_new:
			return False
		self.time = float(ln) 			# get time stamp
		self._changeTime = False
		ln = lns[cnt].strip(); cnt +=1
		node_number = int(ln.split('nddp')[0])
		while True:
			var = lns[cnt]; cnt +=1
			if var.startswith('no fluxes') or var == -1: break
			# read in data
			values = []
			while len(values) != node_number:
				values += lns[cnt].strip().split(); cnt +=1
			# save to attribute
			if var.startswith('temperature') or var.startswith('co2temperat'): 
				self._T = np.array([float(v) for v in values])
			if var.startswith('pressure') or var.startswith('co2pressure'): 
				self._P = np.array([float(v) for v in values])
			if var.startswith('saturation') or var.startswith('wsaturation'): 
				self._S = np.array([float(v) for v in values])
			if var.startswith('lco2saturat'): 
				self._S_co2l = np.array([float(v) for v in values])
			if var.startswith('dissolvdco2'): 
				self._co2aq = np.array([float(v) for v in values])
			if var.startswith('eoswater'): 
				self._eos = np.array([int(v) for v in values])
			if var.startswith('eosco2'): 
				self._co2_eos = np.array([int(v) for v in values])
			if var.startswith('eosdc'): 
				self._dc_eos = np.array([int(v) for v in values])
			if var.startswith('xstress'): 
				self._strs_xx = np.array([float(v) for v in values])
			if var.startswith('ystress'): 
				self._strs_yy = np.array([float(v) for v in values])
			if var.startswith('zstress'): 
				self._strs_zz = np.array([float(v) for v in values])
			if var.startswith('xystress'): 
				self._strs_xy = np.array([float(v) for v in values])
			if var.startswith('xzstress'): 
				self._strs_xz = np.array([float(v) for v in values])
			if var.startswith('yzstress'): 
				self._strs_yz = np.array([float(v) for v in values])
			if var.startswith('xdisplacmnt'): 
				self._disp_x = np.array([float(v) for v in values])
			if var.startswith('ydisplacmnt'): 
				self._disp_y = np.array([float(v) for v in values])
			if var.startswith('zdisplacmnt'): 
				self._disp_z = np.array([float(v) for v in values])
		infile.close()
			
		if self._parent: self._parent._associate_incon()
		
		if if_new: return True
	def write(self,inconfilename=''):
		'''Write out a restart file.
		
		:param inconfilename: Name of restart file to write out.
		:type inconfilename: str
		'''
		if inconfilename: 
			self._path.filename = inconfilename
			#self._parent.files._incon = inconfilename
		if self._parent.work_dir:
			outfile = open(self._path.absolute_to_workdir+slash+self._path.filename,'w')
		else:
			outfile = open(self._path.full_path,'w')
		# write headers
		outfile.write('PyFEHM V1.0                      ')
		import time
		lt = time.localtime()
		mon = str(lt.tm_mon)
		if len(mon) == 1: mon = '0'+mon
		day = str(lt.tm_mday)
		if len(day) == 1: day = '0'+day
		yr = str(lt.tm_year)
		hr = str(lt.tm_hour)
		if len(hr) == 1: hr = '0'+hr
		min = str(lt.tm_min)
		sec = str(lt.tm_sec)
		outfile.write(mon+'/'+day+'/'+yr+'    '+hr+':'+min+':'+sec+'\n')
		outfile.write(self.source+'\n')
		outfile.write('   '+'%20f' % self.time+'\n')
		outfile.write('    '+'%8d' % len(self.T)+' nddp\n')
		# write info
		co2flag = (len(self._co2aq) != 0)
		stressflag = (len(self._strs_xx) != 0)
		if self._parent and co2flag:
			if self._parent.carb.iprtype == 1: co2flag = False
		if self._parent and stressflag:
			if self._parent.strs.param['ISTRS']==0: stressflag = False
		
		headers = ['temperature','saturation','pressure']
		variables = [self.T,self.S,self.P]
		formats = ['%#20.10e','%#20.10e','%#20.10e']
		Ns = [4,4,4]
		nan_subs = [25.,1.,1.]
		if co2flag:
			headers = ['co2temperat','wsaturation','co2pressure','lco2saturat','dissolvdco2',
			'eoswater','eosco2','eosdc']
			variables+=[self._S_co2l,self._co2aq,self._eos,self._co2_eos,self._dc_eos]
			formats += ['%#20.10e','%#20.10e','%1d','%1d','%1d']
			Ns += [4,4,30,30,30]
			nan_subs += [0.,0.,1,1,0]
		if stressflag:
			headers += ['xdisplacmnt','ydisplacmnt','zdisplacmnt','xstress','ystress','xystress',
				'zstress','xzstress','yzstress']
			variables += [self._disp_x,self._disp_y,self._disp_z,self._strs_xx,self._strs_yy,
					self._strs_xy,self._strs_zz,self._strs_xz,self._strs_yz]
			formats += ['%#20.10e','%#20.10e','%#20.10e','%#20.10e','%#20.10e','%#20.10e','%#20.10e',
					'%#20.10e','%#20.10e']
			Ns += [4,4,4,4,4,4,4,4,4]
			nan_subs += [0.,0.,0.,0.,0.,0.,0.,0.,0.,0.,0.]
		
		for header,variable,format,N,nan_sub in zip(headers,variables,formats,Ns,nan_subs):
			if (len(variable) != 0):
				outfile.write(header+'\n')
				cnt = 0
				for val in variable:
					if val != val: val = nan_sub
					if N != 30 and not (header.endswith('ess') or header.endswith('displacmnt')): val = np.max([val,1.e-98])
					outfile.write(format % val + '    ')
					cnt +=1
					if cnt == N: outfile.write('\n'); cnt = 0
				if cnt!=0: outfile.write('\n')		
		outfile.write('no fluxes\n\n')
		outfile.close()
		self._writeOut = False
	def stressgrad(self,xgrad,ygrad,zgrad,xygrad = 0.,xzgrad=0.,yzgrad=0.,calculate_vertical=False,vertical_fraction=False):
		'''Construct initial stress state with vertical stress gradients.
		
		:param xgrad: Vertical gradient in x stress (MPa/m), assumed intercept at [0,0]. If a two element list is given, the first value is interpreted as the gradient, and the second value as the elevation where stress is zero (i.e., the intercept with the z-axis).
		:type xgrad: fl64, list[fl64,fl64]
		:param ygrad: Vertical gradient in y stress (MPa/m), format as for **xgrad**.
		:type ygrad: fl64, list[fl64,fl64]
		:param zgrad: Vertical gradient in z stress (MPa/m), format as for **xgrad**.
		:type zgrad: fl64, list[fl64,fl64]
		:param xygrad: Vertical gradient in xy stress (MPa/m), default is 0, format as for **xgrad**.
		:type xygrad: fl64, list[fl64,fl64]
		:param xzgrad: Vertical gradient in xz stress (MPa/m), default is 0, format as for **xgrad**.
		:type xzgrad: fl64, list[fl64,fl64]
		:param yzgrad: Vertical gradient in yz stress (MPa/m), default is 0, format as for **xgrad**.
		:type yzgrad: fl64, list[fl64,fl64]
		:param calculate_vertical: Vertical stress calculated by integrating density. If true, then zgrad specifies the overburden.
		:type calculate_vertical: bool
		:param vertical_fraction: Horizontal stresses calculated as a fraction of the vertical. If true, xgrad and ygrad are interpreted as fractions.
		:type vertical_fraction: bool
		'''
		if not self.filename: print 'ERROR: initial conditions file containing temperature/pressure data not loaded.'; return
		if not self._parent._associate: print 'ERROR: incon file not associated with parent data file - node and coordinate data not available.'; return
		if vertical_fraction: calculate_vertical = True
		if calculate_vertical:
			print 'NOTE: density integration to obtain vertical stress should only be done for orthogonal meshes'
			if not self._parent._associate: 'ERROR: node property association required to access density data - set associate=True in data file'
			xs = np.unique([nd.position[0] for nd in self._parent.grid.nodelist])
			ys = np.unique([nd.position[1] for nd in self._parent.grid.nodelist])
			# for each x and y, find the column of z-values corresponding
			zs = []
			for x in xs:
				for y in ys:
					zs.append(((x,y),[]))
			zs = dict(zs)
			for nd in self._parent.grid.nodelist:
				zs[(nd.position[0],nd.position[1])].append(nd)
			self._strs_zz = np.zeros((1,self._parent.grid.number_nodes))[0]
			for k in zs.keys():
				zs[k].sort(key=lambda x: x.position[2],reverse=True)
				z0 = zs[k][0].position[2]; sz = [0+zgrad]
				oldRho = zs[k][0].density
				oldZ = zs[k][0].position[2]
				for z in zs[k][1:]:
					sz.append(sz[-1]+9.81*(oldRho+z.density)*abs(z.position[2]-oldZ)/2/1e6)
					oldRho = z.density
					oldZ = z.position[2]
				for nd,szi in zip(zs[k],sz):
					self._strs_zz[nd.index-1] = szi			
			if vertical_fraction:
				self._strs_xx = list(xgrad*np.array(self.strs_zz))
				self._strs_yy = list(ygrad*np.array(self.strs_zz))
				self._strs_xy = list(xygrad*np.array(self.strs_zz))
				self._strs_xz = list(xzgrad*np.array(self.strs_zz))
				self._strs_yz = list(yzgrad*np.array(self.strs_zz))
			else:
				if isinstance(xgrad,tuple) or isinstance(xgrad,list): dx = abs(xgrad[0]); x0 = xgrad[1]
				else: dx = abs(xgrad); x0 = 0
				if isinstance(ygrad,tuple) or isinstance(ygrad,list): dy = abs(ygrad[0]); y0 = ygrad[1]
				else: dy = abs(ygrad); y0 = 0
				if isinstance(xygrad,tuple) or isinstance(xygrad,list): dxy = abs(xygrad[0]); xy0 = xygrad[1]
				else: dxy = abs(xygrad); xy0 = 0
				if isinstance(xzgrad,tuple) or isinstance(xzgrad,list): dxz = abs(xzgrad[0]); xz0 = xzgrad[1]
				else: dxz = abs(xzgrad); xz0 = 0
				if isinstance(yzgrad,tuple) or isinstance(yzgrad,list): dyz = abs(yzgrad[0]); yz0 = yzgrad[1]
				else: dyz = abs(yzgrad); yz0 = 0
				
				z = np.array([nd.position[2] for nd in self._parent.grid.nodelist])
				self._strs_xx = -dx*(z-x0)
				self._strs_yy = -dy*(z-y0)
				self._strs_xy = -dxy*(z-xy0)
				self._strs_xz = -dxz*(z-xz0)
				self._strs_yz = -dyz*(z-yz0)
		else:
			if isinstance(xgrad,tuple) or isinstance(xgrad,list): dx = abs(xgrad[0]); x0 = xgrad[1]
			else: dx = abs(xgrad); x0 = 0
			if isinstance(ygrad,tuple) or isinstance(ygrad,list): dy = abs(ygrad[0]); y0 = ygrad[1]
			else: dy = abs(ygrad); y0 = 0
			if isinstance(zgrad,tuple) or isinstance(zgrad,list): dz = abs(zgrad[0]); z0 = zgrad[1]
			else: dz = abs(zgrad); z0 = 0
			if isinstance(xygrad,tuple) or isinstance(xygrad,list): dxy = abs(xygrad[0]); xy0 = xygrad[1]
			else: dxy = abs(xygrad); xy0 = 0
			if isinstance(xzgrad,tuple) or isinstance(xzgrad,list): dxz = abs(xzgrad[0]); xz0 = xzgrad[1]
			else: dxz = abs(xzgrad); xz0 = 0
			if isinstance(yzgrad,tuple) or isinstance(yzgrad,list): dyz = abs(yzgrad[0]); yz0 = yzgrad[1]
			else: dyz = abs(yzgrad); yz0 = 0
			
			z = np.array([nd.position[2] for nd in self._parent.grid.nodelist])
			self._strs_xx = -dx*(z-x0)
			self._strs_yy = -dy*(z-y0)
			self._strs_zz = -dz*(z-z0)
			self._strs_xy = -dxy*(z-xy0)
			self._strs_xz = -dxz*(z-xz0)
			self._strs_yz = -dyz*(z-yz0)
		self._writeOut = True
		self._stressgradCalled = True
	def critical_stress(self,regime=1,horiz_stress='x',mu=0.6,cohesion=0,proximity=0.,overburden=0.):
		'''Construct initial stress state near Mohr-Coulomb failure. The vertical stress is calculated
		using the assigned density. Minimum or maximum horizontal stress calculated using the specified
		friction coefficient. Intermediate principal stress is assumed to be the average of the other two.
		
		:param regime: Stress regime, 0 = compression, 1 = extension (default).
		:type regime: bool int
		:param horiz_stress: Horizontal coordinate direction ('x' or 'y') to assign the minimum or maximum principal stress (depending on stress regime).
		:type horiz_stress: str
		:param mu: Friction coefficient for Mohr-Coulomb failure (default = 0.6).
		:type mu: fl64
		:param cohesion: Cohesion for Mohr-Coulomb failure (default = 0).
		:type cohesion: fl64
		:param proximity: A negative quantity indicating how close the minimum principal stress is to Mohr-Coulomb failure (MPa, default = 0).
		:type proximity: fl64
		:param overburden: Overburden at top of model (MPa, default = 0).
		:type overburden: fl64
		'''
		mult = np.sqrt(1+mu**2)+mu
		self.stressgrad(xgrad=1.,ygrad=1.,zgrad=overburden,calculate_vertical = True)
		if regime:
			if horiz_stress == 'x':
				self._strs_xx = list((np.array(self.strs_zz)-2*cohesion*mult)/mult**2-proximity)
				self._strs_yy = list((np.array(self.strs_xx)+np.array(self.strs_zz))/2)
			else:
				self._strs_yy = list((np.array(self.strs_zz)-2*cohesion*mult)/mult**2-proximity)
				self._strs_xx = list((np.array(self.strs_yy)+np.array(self.strs_zz))/2)
		else:
			if horiz_stress == 'x':
				self._strs_xx = list(2*cohesion*mult+mult**2*np.array(self.strs_zz)-proximity)
				self._strs_yy = list((np.array(self.strs_xx)+np.array(self.strs_zz))/2)
			else:
				self._strs_yy = list(2*cohesion*mult+mult**2*np.array(self.strs_zz)-proximity)
				self._strs_xx = list((np.array(self.strs_yy)+np.array(self.strs_zz))/2)
	def _summary(self):		
		L = 62
		print ''
		print ' IIII---------------------------------------------------------IIII'
		line = ' IIII FEHM restart file \''+self.filename+'\' summary.'
		for i in range(L-len(line)): line += ' '
		print line+'IIII'
		print ' IIII---------------------------------------------------------IIII'
		
		lines = []
		lines.append(' IIII Restart parameters:')
		if len(self.P): lines.append(' Heat and mass: pressure, temperature, saturation.')
		if len(self.S_co2l): lines.append(' CO2 module: CO2 saturations, dissolve mass, EOS.')
		if len(self.strs_xx): lines.append(' Stress module: normal and shear stresses, displacements.')
		
		for line in lines:
			if line.startswith(' II'):
				for i in range(L-len(line)): line += ' '
				print line+'IIII'
			else:
				prntStr = ' IIII -'
				keepGoing = True
				line = line.split()
				while keepGoing:
					if not line: 
						for i in range(L-len(prntStr)): prntStr += ' '
						print prntStr+'IIII'
						prntStr = ' IIII '
						break
					if len(prntStr)<(L-len(line[0])): 
						prntStr += ' '+line[0]
						line = line[1:]
					else:
						for i in range(L-len(prntStr)): prntStr += ' '
						print prntStr+'IIII'
						prntStr = ' IIII   '
		print ' IIII---------------------------------------------------------IIII'
		print ''
	def _get_filename(self): return self._path.filename
	filename = property(_get_filename)	#: (*str*) Name of restart file (initial conditions)
	def _get_time(self): return self._time
	def _set_time(self,value): self._time = value; self._changeTime = True
	time = property(_get_time,_set_time) 			#: (*fl64*) Time stamp of initial conditions file (end time of simulation that produced this file).
	def _get_T(self): return self._T
	T = property(_get_T) #: (*lst[fl64]*) Initial node temperatures, ordered by node index.
	def _get_P(self): return self._P
	P = property(_get_P)#: (*lst[fl64]*) Initial node pressures, ordered by node index.
	def _get_S(self): return self._S
	S = property(_get_S)#: (*lst[fl64]*) Initial node water saturations, ordered by node index.
	def _get_eos(self): return self._eos
	eos = property(_get_eos)#: (*lst[fl64]*) Initial node water equation of state indices, ordered by node index.
	def _get_co2_eos(self): return self._co2_eos
	co2_eos = property(_get_co2_eos)#: (*lst[fl64]*) Initial node co2 equation of state indices, ordered by node index.
	def _get_S_co2l(self): return self._S_co2l
	S_co2l = property(_get_S_co2l)#: (*lst[fl64]*) Initial node co2 liquid/super-critical saturations, ordered by node index.
	def _get_S_co2g(self): 
		if self.S_co2l == []: return []
		else: return 1-self.S_co2l-self.S
	S_co2g = property(_get_S_co2g)#: (*lst[fl64]*) Initial node co2 gas saturations, ordered by node index.
	def _get_co2aq(self): return self._co2aq
	co2aq = property(_get_co2aq)#: (*lst[fl64]*) Initial node dissolved co2 concentrations, ordered by node index.
	def _get_disp_x(self): return self._disp_x
	disp_x = property(_get_disp_x) #: (*lst[fl64]*) Initial node x displacement, ordered by node index
	def _get_disp_y(self): return self._disp_y
	disp_y = property(_get_disp_y) #: (*lst[fl64]*) Initial node y displacement, ordered by node index
	def _get_disp_z(self): return self._disp_z
	disp_z = property(_get_disp_z) #: (*lst[fl64]*) Initial node z displacement, ordered by node index
	def _get_strs_xx(self): return self._strs_xx
	strs_xx = property(_get_strs_xx) #: (*lst[fl64]*) Initial node x stress, ordered by node index
	def _get_strs_yy(self): return self._strs_yy
	strs_yy = property(_get_strs_yy) #: (*lst[fl64]*) Initial node y stress, ordered by node index
	def _get_strs_zz(self): return self._strs_zz
	strs_zz = property(_get_strs_zz) #: (*lst[fl64]*) Initial node z stress, ordered by node index
	def _get_strs_xy(self): return self._strs_xy
	strs_xy = property(_get_strs_xy) #: (*lst[fl64]*) Initial node xy stress, ordered by node index
	def _get_strs_xz(self): return self._strs_xz
	strs_xz = property(_get_strs_xz) #: (*lst[fl64]*) Initial node xz stress, ordered by node index
	def _get_strs_yz(self): return self._strs_yz
	strs_yz = property(_get_strs_yz) #: (*lst[fl64]*) Initial node yz stress, ordered by node index
	def _get_source(self): return self._source
	source = property(_get_source)					#: (*str*) Name of input file that generated the restart.
class fstrs(object):						#FEHM stress module.
	"""Stress module object, sets properties for execution of FEHM stress module (see macro **STRS**).
	
	"""
	def __init__(self,initcalc=True,fem=True,bodyforce=True,tolerance=-0.01,param={},parent=None):
		self._initcalc=initcalc 			
		self._fem=fem					
		self._parent = parent
		self._bodyforce=bodyforce		
		self._tolerance=tolerance		
		self._param={}					
		self._param['IHMS']=-3
		self._param['ISTRS']=0
		self._param = ImmutableDict(self._param)
		self._excess_she = {}			
		self._excess_she['PAR1']=None
		self._excess_she['PAR2']=None
		self._excess_she['PAR3']=None
		self._excess_she = ImmutableDict(self._excess_she)
		if param: self._param = param
	def __repr__(self): 
		if not self.param['ISTRS']: return 'stress module inactive'
		else: return 'stress module active'
	def on(self):
		"""Set parameters to turn stress calculations ON.
		
		"""
		self.param['ISTRS']=1
		#self._parent.sol['element_integration_INTG']=1
		self._parent.ctrl['stor_file_LDA']=0 		# seg fault when using stress module without this set
	def off(self):
		"""Set param to turn stress calculations OFF.
		
		"""
		self._parent.sol['element_integration_INTG']=-1
		self.param['ISTRS']=0
	def _get_info(self):
		if self.param['ISTRS']: print 'Stress module activated.'
		else: print 'Stress module inactive'; return
		if self.bodyforce: print 'Body forces (gravity) will be calculated.'
		else: print 'Body forces (gravity) will NOT be calculated.'
		if self.initcalc: print 'Initial stress state will be calculated.'
		else: print 'Initial stress state will NOT be calculated.'
	what = property(_get_info)#: Return a summary of the stress module.
	def _get_bodyforce(self): return self._bodyforce
	def _set_bodyforce(self,value): 
		if not(isinstance(value,bool) or value in [0,1]): print 'Boolean values only'; return
		if isinstance(value,int):
			if value == 1: value = True
			elif value == 0: value = False
		self._bodyforce = value
	bodyforce = property(_get_bodyforce,_set_bodyforce)#: (*bool*) Boolean calling for body force calculations (gravity). Default is True.
	def _get_initcalc(self): return self._initcalc
	def _set_initcalc(self,value): 
		if not(isinstance(value,bool) or value in [0,1]): print 'Boolean values only'; return
		if isinstance(value,int):
			if value == 1: value = True
			elif value == 0: value = False
		self._initcalc = value
	initcalc = property(_get_initcalc,_set_initcalc)#: (*bool*) Boolean signalling if initial stress calculations should be performed. Default is True.
	def _get_fem(self): return self._fem
	def _set_fem(self,value): 
		if not(isinstance(value,bool) or value in [0,1]): print 'Boolean values only'; return
		if isinstance(value,int):
			if value == 1: value = True
			elif value == 0: value = False
		self._fem = value
	fem = property(_get_fem,_set_fem)#: (*bool*) Boolean signalling use of finite element modules for calculating stress and displacement. Default is True.
	def _get_tolerance(self): return self._tolerance
	def _set_tolerance(self,value): self._tolerance=value
	tolerance = property(_get_tolerance,_set_tolerance)#: (*flt*) Tolerance of stress calculations.
	def _get_param(self): return self._param
	def _set_param(self,value): self._param = value
	param = property(_get_param, _set_param) #: (*dict[flt]*) Dictionary of stress parameters: 'IHMS' - coupling parameter, 'ISTRS' - type of stress solution.
	def _get_excess_she(self): return self._excess_she
	def _set_excess_she(self,value): self._excess_she = value
	excess_she = property(_get_excess_she, _set_excess_she) #: Dictionary of excess shear parameters:
class fngas(object): 						#FEHM noncondensible gas transport.
	"""Module for noncondensible gas transport (see macro **NGAS**).
	"""
	def __init__(self, parent=None, dof = None):
		self._parent=parent
		self._dof = dof
		self._init_pres = {}
		self._ncg_pres = {}
		self._source = {}
	def __repr__(self):
		if self.dof == None: return 'ncg module inactive'
		else: return 'ncg module active'
	def add_init_pres(self,zone,init_pres):
		if isinstance(zone,tuple):	key = zone
		else: key = zone.index
		self.init_pres.update(dict(((key,init_pres),)))
	def add_ncg_pres(self,zone,ncg_pres):
		if isinstance(zone,tuple):	key = zone
		else: key = zone.index
		self.ncg_pres.update(dict(((key,ncg_pres),)))
	def add_source(self,zone,source):
		if isinstance(zone,tuple):	key = zone
		else: key = zone.index
		self.source.update(dict(((key,source),)))
	def _get_init_pres(self): return self._init_pres
	init_pres = property(_get_init_pres) #: (*dict*) dictionary of initial partial pressures indexed by zone number.
	def _get_ncg_pres(self): return self._ncg_pres
	ncg_pres = property(_get_ncg_pres) #: (*dict*) dictionary of noncondensible pressures indexed by zone number.
	def _get_source(self): return self._source
	source = property(_get_source) #: (*dict*) dictionary of air sources indexed by zone number.
	def _get_dof(self): return self._dof
	def _set_dof(self,value): self._dof = value
	dof = property(_get_dof, _set_dof) #: (*int*) 	degree of freedom (1-3) for the calculation
class fcarb(object):						#FEHM CO2 module.
	"""CO2 module object, sets properties for execution of FEHM CO2 module (see macro **CARB**).
	
	"""
	def __init__(self,iprtype=1,brine=False,parent=None):
		self._iprtype = iprtype 		
		self._brine = brine			
		self._parent =parent
	def __repr__(self): 
		if not self.iprtype==1: return 'CO2 module inactive'
		else: return 'CO2 module active'
	def on(self,iprtype=3):
		"""Set parameters to turn CO2 calculations ON.
		
		:param iprtype: Integer denoting type of simulation (1 = water only, 2 = CO2 only, 3 = water+CO2, no solubility, 4 = water+CO2, with solubility, 5 = water+CO2+air, with solubility)
		:type iprtype: int
		
		"""
		self.iprtype = iprtype
	def off(self):
		"""Set parameters to turn CO2 calculations OFF.
		
		"""
		self.iprtype = 1
	def _get_info(self):
		if self.iprtype != 1: print 'CO2 module activated.'
		else: print 'CO2 module inactive'; return
		prntStr = 'Components:'
		if self.iprtype == 2: prntStr += 'CO2 only'
		elif self.iprtype == 3:prntStr += 'CO2, water (no solubility)'
		elif self.iprtype == 4:prntStr += 'CO2, water (with solubility)'
		elif self.iprtype == 5:prntStr += 'CO2, water, air (with solubility)'		
		print prntStr
		if self.brine: print 'CO2 solubility dependent on brine concentration.'
		else: print 'CO2 solubility NOT dependent on brine concentration.'
	what = property(_get_info)#: Return a summary of the CO2 module.
	def _get_iprtype(self): return self._iprtype
	def _set_iprtype(self,value): self._iprtype = value
	iprtype = property(_get_iprtype, _set_iprtype) #: (*int*) Integer indicating type of simulation.
	def _get_brine(self): return self._brine
	def _set_brine(self,value): self._brine = value
	brine = property(_get_brine, _set_brine) #: (*bool*) Boolean signalling calculation of brine in simulation.
class ftrac(object): 						#FEHM chemistry module.
	"""Chemistry module object, sets properties for execution of FEHM chemistry module (see macro **TRAC**).
	
	"""
	def __init__(self, parent=None, ldsp=False):
		self._param=ImmutableDict(copy(dflt.trac))	
		self._on=False
		self._ldsp = ldsp
		self._specieslist = []
		self._common_modellist = []
		self._common_model_key = None
		self._transport_porosity = -1
		self._parent = parent
	def on(self): 
		"""Switches on the **TRAC** macro. This occurs automatically when the first species object is added.
		"""
		self._on = True
	def off(self): 
		"""Switches off the **TRAC** macro. This occurs automatically when the las species object is deleted.
		"""
		self._on = False
	def add_species(self,phase,adsorption_model=0,adsorption=[],diffusion_model=0,diffusion=1.e-9,
			dispersion = [.0005,.0005,.0005],species=None):
		"""Add a new species to **TRAC**. The new species is accessible via the last item in the specieslist attribute.
		
		:param phase: Flag indicating the phase of the species.
		:type phase: int
		:param adsorption_model: Flag for desired adsorption model (default 0).
		:type adsorption_model: int
		:param adsorption: Adsorption model parameters - three element list.
		:type adsorption: lst[fl64]
		:param diffusion_model: Flag for diffusion model (default 0).
		:type diffusion_model: int
		:param diffusion: Diffusion coefficien (default 1.e-9).
		:type diffusion: fl64
		:param dispersion: Three item list containing X,Y,Z dispersion coefficients. If the ldsp attribute is set to true, the first two entries are interpreted as longitudinal and transverse dispersion, and the third is ignored.
		:type dispersion: lst[fl64]
		:param species: Pre-defined fspecies object.
		:type species: fspecies
		"""
		if not species:
			species = fspecies(phase = phase,adsorption_model=adsorption_model,	adsorption=adsorption,
					diffusion_model=diffusion_model, diffusion=diffusion,dispersion=dispersion)
		species._parent = self
		self._specieslist.append(species)
		if self.number_species == 1: self._on = True	# only switch on if first species added
	def delete_species(self,species):
		"""Delete a species from ftrac.
		
		:param species: Species object to be removed.
		:type species: fspecies
		"""
		self._specieslist.remove(species)
		if self.number_species == 0: self._on = False 	# switch off if no species remain
	def add_common_model(self, zone = None, diffusion_model = 0, diffusion = 1.e-9, dispersion = [0.005,0.005,0.005]):
		"""Add a new common dispersion/diffusion model for multiple species (see GROUP 9 entry of macro **TRAC** in FEHM user manual).
		
		:param zone: Zone to which these parameters are applied.
		:type zone: int, str, fzone
		:param diffusion_model: Flag for desired diffusion model (default 0).
		:type diffusion_model: int
		:param diffusion: Diffusion coefficien (default 1.e-9).
		:type diffusion: fl64
		:param dispersion: Three item list containing X,Y,Z dispersion coefficients. If the ldsp attribute is set to true, the first two entries are interpreted as longitudinal and transverse dispersion, and the third is ignored.
		:type dispersion: lst[fl64]		
		"""
		cm = _common_model(zone = zone, diffusion = diffusion, dispersion = dispersion, diffusion_model = diffusion_model)
		if isinstance(cm.zone,int) or isinstance(cm.zone,str):
			if cm.zone in self._parent.zone.keys(): cm.zone = self._parent.zone[cm.zone]
		self._common_modellist.append(cm)
	def _get_number_species(self): return len(self._specieslist)
	number_species = property(_get_number_species) #: (*int*) Number of species for which transport properties have been defined.
	def _get_ldsp(self): return self._ldsp
	def _set_ldsp(self,value): self._ldsp = value
	ldsp = property(_get_ldsp,_set_ldsp) #: (*bool*) Boolean signalling longitudinal/transverse description of dispersivities to be used.
	def _get_common_modellist(self): return self._common_modellist
	def _set_common_modellist(self,value): self._common_modellist = value
	common_modellist = property(_get_common_modellist,_set_common_modellist) #: (*lst*) List of common model definitions.
	def _get_common_model(self): 
		tempDict = []
		for cm in self._common_modellist:
			if isinstance(cm.zone,list):
				tempDict.append((tuple(cm.zone),cm))
			elif isinstance(cm.zone,int):
				tempDict.append((cm.zone,cm))
		return dict(tempDict)
	common_model = property(_get_common_model) #: (*dict*) Dictionary of common models.
	def _get_param(self): return self._param
	def _set_param(self,value): self._param = value
	param = property(_get_param,_set_param) #: (*dict*) Dictionary of **TRAC** parameters.
	def _get_transport_porosity(self): return self._transport_porosity
	def _set_transport_porosity(self,value): self._transport_porosity = value
	transport_porosity = property(_get_transport_porosity,_set_transport_porosity) #: (*fl64*) Transport porosity for entire domain (zone by zone not supported).
	def _get_specieslist(self): return self._specieslist
	def _set_specieslist(self,value): self._specieslist = value
	specieslist = property(_get_specieslist,_set_specieslist) #: (*lst*) List of species objects.
class fspecies(object):							# class for species transport model
	"""Object for each chemical species. The species transport, adsorption, initial concentration and generator
	properties are assigned in here.
	
	"""
	def __init__(self,phase,adsorption_model,adsorption,diffusion_model,diffusion, dispersion):
		self._phase = phase
		self._parent = None
		
		self._adsorption_model = adsorption_model
		if adsorption:
			if len(adsorption) != 3: print 'ERROR: expecting three adsorption parameters'; return
			self._adsorption = adsorption
		self._diffusion_model = diffusion_model
		self._dispersion = dispersion
		self._diffusion = diffusion
		self._density_modifier = None
		
		self._tracer_concentrationlist = []
		self._tracer_generatorlist = []
	def add_tracer_concentration(self,initial_concentration,zone=None):
		"""Define initial tracer concentration in a zone.
		
		:param initial_concentration: Initial concentration of the tracer.
		:type initial_concentration: fl64
		:param zone: Zone to which the initial concentration is assigned (default Zone 0).
		:type zone: int, str, fzone
		"""
		if not zone: zone = self._parent._parent.zone[0]
		ic = _tracer_concentration(initial_concentration,zone)
		self._tracer_concentrationlist.append(ic)
	def delete_tracer_concentration(self,tracer_concentration):
		self._tracer_concentrationlist.remove(tracer_concentration)		
	def add_tracer_generator(self,tracer_generator,time_start,time_end,zone=None):
		"""Define a tracer source or sink within a zone.
		
		:param tracer_generator: Injection concentration at inlet node. If outlet, in place concentration will be used. If negative, concentration will be fixed at the absolute value.
		:type tracer_generator:fl64
		:param time_start: Time to start the source/sink.
		:type time_start:fl64
		:param time_end: Time to stop the source/sink.
		:type time_end: fl64
		"""
		if not zone: zone = self._parent._parent.zone[0]
		ic = _tracer_generator(tracer_generator,time_start,time_end,zone)
		self._tracer_generatorlist.append(ic)
	def delete_tracer_generator(self,tracer_generator):
		self._tracer_generatorlist.remove(tracer_generator)
	def _get_phase(self): return self._phase
	def _set_phase(self,value): self._phase = value
	phase = property(_get_phase,_set_phase) #: (*int*) Flag for species phase.
	def _get_adsorption_model(self): return self._adsorption_model
	def _set_adsorption_model(self,value): self._adsorption_model = value
	adsorption_model = property(_get_adsorption_model,_set_adsorption_model) #: (*int*) Flag for adsorption model.
	def _get_adsorption(self): return self._adsorption
	def _set_adsorption(self,value): self._adsorption = value
	adsorption = property(_get_adsorption,_set_adsorption) #: (*lst[fl64]*) Three item list of adsoprtion parameters.
	def _get_diffusion_model(self): return self._diffusion_model
	def _set_diffusion_model(self,value): self._diffusion_model = value
	diffusion_model = property(_get_diffusion_model,_set_diffusion_model) #: (*int*) Flag for diffusion model.
	def _get_diffusion(self): return self._diffusion
	def _set_diffusion(self,value): self._diffusion = value
	diffusion = property(_get_diffusion,_set_diffusion) #: (*fl64*) Diffusion coefficient.
	def _get_dispersion(self): return self._dispersion
	def _set_dispersion(self,value): self._dispersion = value
	dispersion = property(_get_dispersion,_set_dispersion) #: (*lst[fl64]*)	Three item list of X,Y,Z dispersion coefficients, or longitudinal and transverse components if ldsp = True.
	def _get_density_modifier(self): return self._density_modifier
	def _set_density_modifier(self,value): self._density_modifier = value
	density_modifier = property(_get_density_modifier,_set_density_modifier) #: (*fl64*) Density modifier used in macro **CDEN**. If set, **CDEN** output will be written along with **TRAC**.
	def _get_tracer_concentrationlist(self): return self._tracer_concentrationlist
	def _set_tracer_concentrationlist(self,value): self._tracer_concentrationlist = value
	tracer_concentrationlist = property(_get_tracer_concentrationlist,_set_tracer_concentrationlist) #: (*lst*) List of initial tracer concentration objects.
	def _get_tracer_generatorlist(self): return self._tracer_generatorlist
	def _set_tracer_generatorlist(self,value): self._tracer_generatorlist = value
	tracer_generatorlist = property(_get_tracer_generatorlist,_set_tracer_generatorlist) #: (*lst*) List of tracer generator objects.
class _common_model(object):
	def __init__(self, zone, diffusion_model, diffusion, dispersion):
		self._zone = zone
		self._diffusion = diffusion
		self._dispersion = dispersion
		self._diffusion_model = diffusion_model
	def _get_zone(self): return self._zone
	def _set_zone(self,value): self._zone = value
	zone = property(_get_zone,_set_zone) #: (**)
	def _get_diffusion(self): return self._diffusion
	def _set_diffusion(self,value): self._diffusion = value
	diffusion = property(_get_diffusion,_set_diffusion) #: (**)
	def _get_diffusion_model(self): return self._diffusion_model
	def _set_diffusion_model(self,value): self._diffusion_model = value
	diffusion_model = property(_get_diffusion_model,_set_diffusion_model) #: (**)
	def _get_dispersion(self): return self._dispersion
	def _set_dispersion(self,value): self._dispersion = value
	dispersion = property(_get_dispersion,_set_dispersion) #: (**)
class _tracer_concentration(object):
	def __init__(self,initial_concentration,zone = None):
		self._zone = zone
		self._initial_concentration = initial_concentration
	def _get_zone(self): return self._zone
	def _set_zone(self,value): self._zone = value
	zone = property(_get_zone,_set_zone) #: (**)
	def _get_initial_concentration(self): return self._initial_concentration
	def _set_initial_concentration(self,value): self._initial_concentration = value
	initial_concentration = property(_get_initial_concentration,_set_initial_concentration) #: (**)
class _tracer_generator(object):
	def __init__(self,injection_concentration, time_start, time_end ,zone = None):
		self._zone = zone
		self._injection_concentration = injection_concentration
		self._time_start = time_start
		self._time_end = time_end
	def _get_injection_concentration(self): return self._injection_concentration
	def _set_injection_concentration(self,value): self._injection_concentration = value
	injection_concentration = property(_get_injection_concentration,_set_injection_concentration) #: (**)
	def _get_time_start(self): return self._time_start
	def _set_time_start(self,value): self._time_start = value
	time_start = property(_get_time_start,_set_time_start) #: (**)
	def _get_time_end(self): return self._time_end
	def _set_time_end(self,value): self._time_end = value
	time_end = property(_get_time_end,_set_time_end) #: (**)
	def _get_zone(self): return self._zone
	def _set_zone(self,value): self._zone = value
	zone = property(_get_zone,_set_zone) #: (**)
class fcont(object):						#FEHM contour output object.
	"""Contour output object, makes request for contour data to be output (see macro **CONT**).
	
	This data type outputs specified variables (e.g., temperature, permeability) for x,y,z or node locations
	at fixed times (one file = one time). The data can be output in several formats (all of which are readable by
	PyFEHM) and at specified times.
	"""
	def __init__(self,type=dflt.cont_format,timestep_interval=1000,time_interval=1.e30,time_flag=True,variables=[],zones=[]):
		self._type = type 			
		self._timestep_interval=timestep_interval 
		self._time_interval=time_interval		
		self._time_flag=time_flag		
		self._variables=[] 			
		if variables: self.variables=variables
		self._zones=[]
		if zones: self.zones=zones
	def __repr__(self): 
		retStr = self.type + ' contour output:\n'
		for v in list(flatten(self.variables)):
			retStr += v+'\n'
		return retStr
	def _get_options(self): 							#print out available variables
		print 'The following are acceptable variables'
		allVariables = list(flatten(self.variables))
		for var in contour_variables: 
			for v in var: 
				if v in allVariables: print '    '+v +' (selected)'
				else: print '    '+v
	options = property(_get_options) 		#: Print out eligible variables for output.
	def _get_info(self):
		print 'Contour output requested ('+self.type+' format): '
		print '    every ' + str(self.timestep_interval)+ ' timesteps'
		print '    every ' + str(self.time_interval)+ ' days'
		print '    for variables:'
		for var in list(flatten(self.variables)):
			print '         '+var
		print 
	what = property(_get_info) 				#: Print out information about the attribute.
	def _get_type(self): return self._type
	def _set_type(self,value): self._type = value
	type = property(_get_type, _set_type) #: (*str*) File format for contour output: 'tec', 'surf', 'avs', 'avsx'
	def _get_time_interval(self): return self._time_interval
	def _set_time_interval(self,value): self._time_interval = value
	time_interval = property(_get_time_interval, _set_time_interval) #: (*flt*) Time interval to output data.
	def _get_timestep_interval(self): return self._timestep_interval
	def _set_timestep_interval(self,value): self._timestep_interval = value
	timestep_interval = property(_get_timestep_interval, _set_timestep_interval) #: (*int*) Time step interval to output data.
	def _get_variables(self): return self._variables
	def _set_variables(self,value): self._variables = value
	variables = property(_get_variables, _set_variables) #: (*lst[str]*)List of variables to write contour data for, e.g., ['temperature','pressure']
	def _get_zones(self): return self._zones
	def _set_zones(self,value): self._zones = value
	zones = property(_get_zones, _set_zones) #: (*lst[fzone]*) List of zone objects for which contour data is to be written - **NOT FULLY SUPPORTED**.
	def _get_time_flag(self): return self._time_flag
	def _set_time_flag(self,value): self._time_flag = value
	time_flag = property(_get_time_flag, _set_time_flag) #: (*bool*) Set to True to include in output title.
class fhist(object):						#FEHM history output object.
	"""FEHM history output object.
	
	"""
	def __init__(self,type=dflt.hist_format,timestep_interval=1,time_interval=1.e30,variables=[],nodelist=[],zonelist=[],zoneflux=[]):
		self._type = type			
		self._timestep_interval=timestep_interval	
		self._time_interval=time_interval	
		self._variables=[]			
		self._nodelist=[]
		if nodelist: self._nodelist = nodelist
		self._zonelist=[]
		if zonelist: self._zonelist = zonelist
		self._zoneflux=[]
		if zoneflux: self._zoneflux = zoneflux
		if variables: self.variables=variables
	def __repr__(self): 
		retStr = self.type + ' history output:\n'
		for v in self.variables:
			retStr += v[0]+'\n'
		return retStr
	def _get_options(self): 							#print out available variables
		print 'The following are acceptable variables'
		for var in history_variables:
			if var in self.variables: print var +' (selected)'
			else: print var
	options = property(_get_options) 		#: Print out eligible variables for output.
	def _get_nodelist(self): return self._nodelist
	def _set_nodelist(self,value): self._nodelist = value
	nodelist = property(_get_nodelist, _set_nodelist) #: (*list[fnode]*) list of node objects for which history output requested.
	def _get_node(self): return dict([(nd.index,nd) for nd in self.nodelist])
	node = property(_get_node) #: (*dict[fnode]*) Dictionary of nodes, indexed by node number, for which history output requested.
	def _get_zonelist(self): return self._zonelist
	def _set_zonelist(self,value): self._zonelist = value
	zonelist = property(_get_zonelist, _set_zonelist) #: (*lst[fzone]*) List of zone objects for which history output required.
	def _get_zoneflux(self): return self._zoneflux
	def _set_zoneflux(self,value): self._zoneflux = value
	zoneflux = property(_get_zoneflux, _set_zoneflux) #: (*lst[fzone,int]*) List of zone objects for which zone flux output required.
	def _get_zone(self): return dict([(zn.index,zn) for zn in self.zonelist]+[(zn.name,zn) for zn in self.zonelist if zn.name != ''])
	zone = property(_get_zone) #: (*dict[fzone]*) Dictionary of zones, indexed by number and name, for which history output is required.
	def _get_info(self):
		print 'History output requested ('+self.type+' format): '
		if self.timestep_interval == None:
			print '    every timestep'
		else:
			print '    every ' + str(self.timestep_interval)+ ' timesteps'
		if self.time_interval == None:
			print '    every ' + str(1.e30)+ ' days'
		else:
			print '    every ' + str(self.time_interval)+ ' days'
		print '    for variables:'
		for var in list(flatten(self.variables)):
			print '         '+var
		if self.nodelist:
			print '    at nodes:'
			for nd in self.nodelist:
				print '         '+str(nd.index)
		if self.zonelist:
			print '    for zones:'
			for zn in self.zonelist:
				if zn.name: 
					print '         '+str(zn.index)+' ('+zn.name+')'
				else: 
					print '         '+str(zn.index)
		print 
	what = property(_get_info) 				#: Print out information about the attribute.
	def _get_variables(self): return self._variables
	def _set_variables(self,value): self._variables = value
	variables = property(_get_variables, _set_variables) #: (*lst[str]*)List of variables to write contour data for, e.g., ['temperature','pressure']
	def _get_type(self): return self._type
	def _set_type(self,value): self._type = value
	type = property(_get_type, _set_type) #: (*str*) File format for contour output: 'tecplot', 'csv', 'surfer'
	def _get_timestep_interval(self): return self._timestep_interval
	def _set_timestep_interval(self,value): self._timestep_interval = value
	timestep_interval = property(_get_timestep_interval, _set_timestep_interval) #: (*int*) Time step interval to output data.
	def _get_time_interval(self): return self._time_interval
	def _set_time_interval(self,value): self._time_interval = value
	time_interval = property(_get_time_interval, _set_time_interval) #: (*flt*) Time interval to output data.
class fboun(object):						#FEHM boundary condition object.
	'''Boundary condition object.
	
	'''
	def __init__(self,zone=[],type='ti',times=[],variable=[],file=None):
		self._zone = []					
		if zone: self.zone=zone
		self._type = type 				
		self._times=times	
		self._parent = None
		self._variable = []			
		self._file = file	
		if variable: self.variable = variable
	def __repr__(self): 
		retStr = self.type + ' BC: variable = ' 
		for var in self.variable: retStr += var[0] + ', '
		return retStr
	def _get_information(self):
		prntStr = 'Boundary condition for zones: '
		for zn in self.zone: 
			if isinstance(zn,fzone): prntStr += str(zn.index)+', '
			else: prntStr += str(zn) + ', '
		prntStr = prntStr[:-2]
		print prntStr
	what = property(_get_information)	#: Print information about the boundary condition object.
	def _get_zone(self): return self._zone
	def _set_zone(self,value): 
		if isinstance(value,fzone):	value = [value,]
		self._zone = value
	zone = property(_get_zone,_set_zone)#: (*lst[fzone]*) List of zones to which the boundary condition is to be applied.
	def _get_type(self): return self._type
	def _set_type(self,value): self._type = value
	type = property(_get_type,_set_type)#: (*str*) Boundary condition type, 'ti' = step changes, 'ti_linear' = linear changes.
	def _get_n_times(self): return len(self.times) 
	n_times = property(_get_n_times)#: (*int*) Length of time-series.
	def _get_variable(self): return self._variable
	def _set_variable(self,value): self._variable = value
	variable = property(_get_variable,_set_variable)#: (*lst[lst[str,fl64,...]]*) List of lists of boundary data. Each list begins with a string denoting the boundary condition variable, and is followed by the time-series data, e.g., ['sw',0.2,0.5,0.8].
	def _get_times(self): return self._times
	def _set_times(self,value): self._times=value
	times = property(_get_times,_set_times)#: (*lst[fl64]*) Vector of times.
	def _get_file(self): return self._file
	def _set_file(self,value): self._file = value
	file = property(_get_file,_set_file)#: (*str*) File string where information about the macro is stored. If file does not currently exist, it will be created and written to when the FEHM input file is written.
	def _check(self):
		# check length of variable vectors correspond to length of time vectors
		for var in self._variable:
			if len(var)-1<len(self.times):
				prntStr = 'WARNING: Variable vector ('+var[0]+') specified in BOUN macro shorter than time vector.'
			if len(var)-1>len(self.times):
				prntStr = 'WARNING: Variable vector ('+var[0]+') specified in BOUN macro longer than time vector.'
class frlpm(object): 						#FEHM relative permeability object (different to rlp macro).
	'''Relative permeability model.
	
	Relative permeability models are applied to zones. Each model assigns the relative permeability characteristics
	for a particular phase (in attribute relperm) and capillary pressure relationships between phases (in attribute capillary).
	In contrast to other macros, one relative permeability model may be applied to multiple zones.
	'''
	def __init__(self,zone=[],group = None,relperm=[],capillary=[]):
		self._zone=[]
		if zone: self._zone = zone
		self._group = None
		if group: self._group = group
		self._relperm = ImmutableDict({})
		if relperm: self._assign_relperm(relperm)
		self._capillary = ImmutableDict({})
		if capillary: self._assign_capillary(capillary)
		self._parent = None
	def __repr__(self):
		prntStr = 'rlpm: '
		if isinstance(self.zone,fzone): prntStr += str(self.zone.index)
		elif isinstance(self.zone,list): 
			for zn in self.zone: prntStr += str(self.zone.index)+ ' ,'
			prntStr = prntStr[:-2]
		elif isinstance(self.zone,tuple):
			zn = self.zone
			prntStr += '('+str(zn[0]) +', '	+str(zn[1]) +', '+str(zn[2]) +')'
		return prntStr
	def _assign_relperm(self,relperms):
		for relperm in relperms:
			if not (isinstance(relperm,list) or isinstance(relperm,tuple)): continue
			if len(relperm) != 3: print 'relperms specified incorrectly'; continue
			self.add_relperm(relperm[0],relperm[1],relperm[2])
	def _assign_capillary(self,capillarys):
		for capillary in capillarys:
			if not (isinstance(capillary,list) or isinstance(capillary,tuple)): continue
			if len(capillary) != 3: print 'capillarys specified incorrectly'; continue
			self.add_capillary(capillary[0],capillary[1],capillary[2])
	def add_relperm(self,phase,type,param=[]):
		'''Add a new relative permeability model for a given phase.
		
		:param phase: Phase for which the relperm model is being defined, e.g., 'air','water','co2_liquid','co2_gas','vapor'.
		:type phase: str
		:param type: Type of model being assigned for that phase, e.g., 'constant','linear','exponential','corey','brooks-corey','vg' (Van Genuchten).
		:type type: str
		:param param: List of parameters for the specified model. See table above for a list of parameter names for each model.
		:type param: list
		'''
		if param:
			new_relperm = _relperm(phase,type,param)
		else: new_relperm = _relperm(phase,type)
		self._relperm.update(dict(((new_relperm.phase,new_relperm),)))
	def add_capillary(self,phase,type,param=[]):
		'''Add a new capillary pressure relationship between two phases.
		
		:param phase: List or tuple of two phases for which the relationship is defined, e.g., ['air','water'].
		:type phase: list, tuple
		:param type: Type of model being assigned for that phase pair, e.g., 'linear_cap','vg_cap','brooks-corey_cap'.
		:type type: str
		:param param: List of parameters for the specified model. See table above for a list of parameter names for each model.
		:type param: list
		'''
		if param:
			new_capillary = _relperm(phase,type,param)
		else: new_capillary = _relperm(phase,type)
		self._capillary.update(dict(((new_capillary.phase,new_capillary),)))
	def delete(self,model):
		"""Delete a previously defined relative permeability or capillary pressure model.
		"""
		if isinstance(model,_relperm): model = relperm.phase
		if model in self._relperm.keys(): self._relperm.__delitem__(model)
		if model in self._capillary.keys(): self._capillary.__delitem__(model)
	def _get_relperm(self): return self._relperm
	relperm = property(_get_relperm) #: (*dict*) Dictionary of relative permeability models for each phase, indexed by phase name, e.g., 'water'. Each relperm model has a model type, and set of parameters for that type.
	def _get_capillary(self): return self._capillary
	capillary = property(_get_capillary) #: (*dict*) Dictionary of capillary pressure models, indexed by a tuple phase name pair, e.g., ('water/air'). Each capillary pressure model has a model type, and set of parameters for that type.
	def _get_zone(self): return self._zone
	def _set_zone(self,value): self._zone = value
	zone = property(_get_zone, _set_zone) #: (*fzone*) Zone or list of zones to which the relative permeability model is assigned.
	def _get_group(self): return self._group
	def _set_group(self,value): self._group = value
	group = property(_get_group, _set_group) #: (*int*) Group assignment for the relative permeability model.
	def _get_phases(self):
		if len(self.relperm) == 0: return []
		else:
			return [self.relperm[k].phase for k in self.relperm.keys()]
	phases = property(_get_phases)
class _relperm(object): 						# private class for relative permeability model
	def __init__(self,phase,type,param=[]):
		self._type = type
		self._phase = phase
		self._param = None
		self._assign_param()
		if param: self._set_param(param)
	def __repr__(self):
		return self.phase + ' - ' + self.type 	
	def _assign_param(self):
		'''Assign parameters if supplied on initialisation.'''
		self._param = dict(rlpm_dicts[self.type])
		self._param = ImmutableDict(self._param)
	def _set_param(self,param):
		if len(param) != len(self.param.keys()): return		# return if numbers don't match up
		for par,key in zip(param,rlpm_dicts[self.type]):
			if isinstance(par,list) or isinstance(par,tuple):
				self._param[par[0]] = par[1]
			else:
				self._param[key[0]] = par
	def _get_phase(self): return self._phase
	def _set_phase(self,value): 
		if value not in rlpm_phases: print 'WARNING: '+str(value)+' not an available phase.';return
		self._phase = value
	phase = property(_get_phase, _set_phase) #: (**)
	def _get_type(self): return self._type
	def _set_type(self,value): 
		if value == self._type: return
		if value not in rlpm_dicts.keys(): print 'WARNING: '+str(value)+' not an available model.';return
		self._type = value
		self._param = ImmutableDict(rlpm_dicts[value])
	type = property(_get_type, _set_type) #: (**)
	def _get_param(self): return self._param
	param = property(_get_param) #: (**)		
class frlpm_table(object):						# different object for specifying tables
	"""Specify relative permeablity relationships using a lookup table. 
	
	Lookup tables can offer computational time savings where the relative permeability function is difficult to calculate.
	"""
	def __init__(self, zone=[], group=None, saturation=[], phase1 =  [], phase2 = [], capillary=[]):
		self._zone=[]
		if zone: self._zone = zone
		self._group = None
		if group: self._group = group
		self._saturation = None
		if saturation: self._saturation = saturation
		self._phase1 = None
		vars = ['water','h2o_liquid','air','h2o_gas','vapor','co2_gas','co2_liquid','co2_sc']
		if phase1:
			if phase1[0] not in vars: 
				print 'ERROR: first entry of phase1 must be one of ',vars; return
			if not self._saturation:
				print 'ERROR: no saturation data supplied'; return
			if len(phase1[1]) != len(self._saturation):
				print 'ERROR: length of supplied phase1 relperm vector does not match saturation data'; return
			self._phase1 = phase1
		if phase2:
			if phase2[0] not in vars: 
				print 'ERROR: first entry of phase2 must be one of ',vars; return
			if not self._saturation:
				print 'ERROR: no saturation data supplied'; return
			if len(phase1[1]) != len(self._saturation):
				print 'ERROR: length of supplied phase2 relperm vector does not match saturation data'; return
			self._phase2 = phase2
		if capillary:
			if not self._saturation:
				print 'ERROR: no saturation data supplied'; return
			if len(capillary) != len(self._saturation):
				print 'ERROR: length of supplied capillary vector does not match saturation data'; return
			self._capillary = capillary		
		self._parent = None	
	def _get_zone(self): return self._zone
	def _set_zone(self,value): self._zone = value
	zone = property(_get_zone, _set_zone) #: (*fzone*) Zone or list of zones to which the relative permeability model is assigned.
	def _get_group(self): return self._group
	def _set_group(self,value): self._group = value
	group = property(_get_group, _set_group) #: (*int*) Group assignment for the relative permeability model.
	def _get_saturation(self): return self._saturation
	def _set_saturation(self,value): self._saturation = value
	saturation = property(_get_saturation, _set_saturation) #: (*lst*) List or array of saturation values for which relperm data are supplied.
	def _get_phase1(self): return self._phase1
	def _set_phase1(self,value): self._phase1 = value
	phase1 = property(_get_phase1, _set_phase1) #: (*lst*) A two item list containing a string denoting the wetting phase, e.g., 'water','co2_liquid', and a vector of relperm data corresponding to the values in the saturation attribute.
	def _get_phase2(self): return self._phase2
	def _set_phase2(self,value): self._phase2 = value
	phase2 = property(_get_phase2, _set_phase2) #: (*lst*) A two item list containing a string denoting the non-wetting phase, e.g., 'water','co2_liquid', and a vector of relperm data corresponding to the values in the saturation attribute.
	def _get_capillary(self): return self._capillary
	def _set_capillary(self,value): self._capillary = value
	capillary = property(_get_capillary, _set_capillary) #: (*lst*) List or array of capillary pressure values corresponding to the supplied saturation data for the phase pair.def _get_phases:
	def _get_phases(self):
		phs = []
		if len(self.phase1)>0: phs.append(self.phase1[0])
		if len(self.phase2)>0: phs.append(self.phase2[0])
		return phs
	phases = property(_get_phases) 	#: (*lst*) List of phases for which relperm properties have been defined.
class files(object):						#FEHM file constructor.
	'''Class containing information necessary to write out fehmn.files.
	'''
	
	def __init__(self,root='',input='',grid='',incon='',rsto='',outp='',check='',hist='',co2in='',stor='',exe='fehm.exe',verbose=True):
		self._root = ''
		self._input = ''
		self._grid = ''
		self._incon = ''
		self._use_incon = False
		self._rsto = ''
		self._use_rsto = True
		self._outp = ''
		self._use_outp = False
		self._check = ''
		self._use_check = False
		self._hist = ''
		self._use_hist = False
		self._co2in = ''
		self._use_co2in = False
		self._stor = ''
		self._use_stor = False		
		self._parent = None
		self._exe = exe
		self._verbose = verbose
		if root:  	# if root specified assign as default for all inputs.
			self._root = root
			self._assign_root()
		if input: self._input = input
		if grid: self._grid = grid
		if incon: self._incon = incon; self._use_incon = True
		if rsto: self._rsto = rsto; self._use_rsto = True
		if outp: self._outp = outp; self._use_outp = True
		if check: self._check = check; self._use_check = True
		if hist: self._hist = hist; self._use_hist = True
		if stor: self._stor = stor; self._use_stor = True
	def __repr__(self): return 'fehmn.files constructor for '+str(self.input)	
	def _assign_root(self):
		'''Use root name for all inputs.
		'''
		self._root = root
		self._input = root+'.dat'
		self._grid = root+'.inp'
		self._rsto = root+'.fin'
		self._outp = root+'.out'
		self._check = root+'.chk'
		self._hist = root+'.his'
	def write(self):
		'''Write out *fehmn.files*.
		'''		
		
		if self._parent.work_dir:
			outfile = open(self._parent.work_dir+slash+'fehmn.files','w')
		else:
			outfile = open('fehmn.files','w')
			
		outfile.write('input: '+self.input+'\n')
		outfile.write('grida: '+self.grid+'\n')
		if not self.root: self.root = self.input.split('.')[0]
		
		if not self.rsto: self.rsto = self.root+'.rsto' 			# default is to produce a restart file
		outfile.write('rsto: '+self.rsto+'\n')
		
		if self._use_outp: 
			if not self.outp: self.outp = self.root+'.outp'
			outfile.write('outp: '+self.outp+'\n')
		if self._use_check: 
			if not self.check: self.check = self.root+'.chk'
			outfile.write('check: '+self.check+'\n')
			
		if self.incon: outfile.write('rsti:'+self.incon+'\n')
		
		if self._use_hist: 
			if not self.check: self.check = self.root+'.hst'
			outfile.write('hist: '+self.hist+'\n')
		
		if self._parent.carb.iprtype != 1 and not self.co2in: 
			self._use_co2in = True
			co2_path = fpath()
			co2_path.filename = dflt.co2_interp_path
			if not os.path.isfile(co2_path.full_path):
				co2_path.filename = dflt.co2_interp_path_2
			if not os.path.isfile(co2_path.full_path):
				print 'WARNING: Cant find co2_interp.txt'
				self._use_co2in = False
		elif self.co2in:
			co2_path = fpath()
			co2_path.filename = self.co2in
			
		if self._use_co2in: 
			outfile.write('co2in: '+co2_path.full_path+'\n')	
			
		if self._use_stor: 
			outfile.write('stor:')	
			if not self.stor: self.stor = self.root+'.stor'
			outfile.write(' '+self.stor)
			outfile.write('\n')
		if self.root: outfile.write('root:'+self.root+'\n')		
		
		# level of print screen output
		if self.verbose: outfile.write('\nall\n')
		else: outfile.write('\nnone\n')
		outfile.close()
	def _get_input(self): return self._input
	def _set_input(self,value):  
		self._input = value
		if self._root == None:
			self._root = self._input.split('.')[0]
	input = property(_get_input,_set_input) #: (*str*) Name of input file. This is set automatically when reading an input file in PyFEHM or when running a simulation.
	def _get_root(self): return self._root
	def _set_root(self,value):  self._root = value
	root = property(_get_root,_set_root)	#: (*str*) Default file name string. If not already specified, this is set automatically when running a simulation.
	def _get_grid(self): return self._grid
	def _set_grid(self,value):  self._grid = value
	grid = property(_get_grid,_set_grid)	#: (*str*) Name of grid file. This is set automatically when reading an grid file in PyFEHM.
	def _get_incon(self): return self._incon
	def _set_incon(self,value):  self._incon = value; self._use_incon = True
	incon = property(_get_incon,_set_incon)	#: (*str*) Name of restart file to read in (initial condition). This is set automatically when reading an incon file in PyFEHM.
	def _get_rsto(self): return self._rsto
	def _set_rsto(self,value):  self._rsto = value
	rsto = property(_get_rsto,_set_rsto)	#: (*str*) Name of restart file to write out.
	def _get_outp(self): return self._outp
	def _set_outp(self,value):  self._outp = value; self._use_outp = True
	outp = property(_get_outp,_set_outp)	#: (*str*) Name of output file.
	def _get_check(self): return self._check
	def _set_check(self,value):  self._check = value
	check = property(_get_check,_set_check)	#: (*str*) Name of check file.
	def _get_co2in(self): return self._co2in
	def _set_co2in(self,value): 
		self._co2in = value
		self._use_co2in = True
	co2in = property(_get_co2in, _set_co2in) #: (*str*) Name or path to co2 properties file
	def _get_hist(self): return self._hist
	def _set_hist(self,value):  self._hist = value
	hist = property(_get_hist,_set_hist)	#: (*str*) Name of history file.
	def _get_stor(self): return self._stor
	def _set_stor(self,value):  self._stor = value; self._use_stor = True
	stor = property(_get_stor,_set_stor)	#: (*str*) Name of store file.
	def _get_exe(self): return self._exe
	def _set_exe(self,value):  self._exe = value
	exe = property(_get_exe,_set_exe)#: (*str*) Path to FEHM executable. Default is 'fehm.exe'.
	def _get_verbose(self): return self._verbose	
	def _set_verbose(self,value):  self._verbose = value
	verbose = property(_get_verbose,_set_verbose)#: (*bool*) Boolean to request FEHM output to screen.
class fdata(object):						#FEHM data file.
	"""Class for FEHM data file. 
	
	"""		
	__slots__ = ['_filename','_gridfilename','_inconfilename','_sticky_zones','_allMacro','_allModel','_associate','_work_dir',
			'_bounlist','_cont','_ctrl','_grid','_incon','_hist','_iter','_nfinv','_nobr','_vapl','_adif','_rlpmlist','_pporlist','_vconlist','_sol',
			'_time','text','times','_time','_zonelist','_writeSubFiles','_strs','_ngas','_carb','_trac','_files','_verbose',
			'_tf','_ti','_dti','_dtmin','_dtmax','_dtn','_dtx','_sections','_help','_running','_unparsed_blocks','keep_unknown','_flxo',
			'_output_times','_path']
	def __init__(self,filename='',gridfilename='',inconfilename='',sticky_zones=dflt.sticky_zones,associate=dflt.associate,work_dir = None,
		full_connectivity=dflt.full_connectivity,skip=[],keep_unknown=dflt.keep_unknown):		#Initialise data file
		from copy import copy
		#self._filename=filename			
		self._gridfilename=gridfilename	
		self._inconfilename=inconfilename 
		self._sticky_zones = sticky_zones
		self._allMacro = dict([(key,[]) for key in macro_list.keys()])
		self._allModel = dict([(key,[]) for key in model_list.keys()])
		self._associate = associate 
#		if work_dir:
#			if not os.path.isdir(work_dir): os.makedirs(work_dir)		
		# model objects
		self._bounlist = []				
		self._cont = fcont()				
		self._ctrl=ImmutableDict(copy(dflt.ctrl))	
		self._grid=fgrid()				
		self.grid._parent = self
		self._incon=fincon() 			
		self.incon._parent = self
		self._hist = fhist()				
		self._iter=ImmutableDict(copy(dflt.iter))	
		self._nfinv = False
		self._nobr = False					
		self._vapl = False					
		self._adif = None
		self._rlpmlist=[]
		self._sol = ImmutableDict(copy(dflt.sol))
		self.text=[]					#: (*str*) Information about the model printed at the top of the input file.
		self._time=ImmutableDict(copy(dflt.time))	
		self.times=[]					
		self._zonelist=[]	
		self._flxo = []
		#self._zone={}				
		self._writeSubFiles = True 		# Boolean indicating macro and zone sub files should be written every time
		# additional modules
		self._strs = fstrs(parent=self)	
		self._carb = fcarb(parent=self)	
		self._trac = ftrac(parent=self)	
		self._ngas = fngas(parent=self)
		self._help = fhelp(parent=self)
		# run object
		self._path = fpath(parent=self)
		#self._path.filename=filename	
		self._files = files() 				
		self._files._parent = self
		self._verbose = True
		self._running = False 		# boolean indicating whether a simulation is in progress
		self._unparsed_blocks = {}
		self.keep_unknown = keep_unknown
		self.work_dir = work_dir
		if self.work_dir:
			try:
				os.makedirs(self.work_dir)
			except:
				pass
		# time stepping shortcuts
		self._tf = dflt.time['max_time_TIMS']
		self._ti = dflt.time['initial_day_INITTIME']
		self._dti = dflt.time['initial_timestep_DAY']
		self._dtmin = dflt.ctrl['min_timestep_DAYMIN']
		self._dtmax = dflt.ctrl['max_timestep_DAYMAX']
		self._dtn = dflt.time['max_timestep_NSTEP']
		self._dtx = dflt.ctrl['timestep_multiplier_AIAA']
		self._output_times = []
		# add 'everything' zone
		self._add_zone(fzone(index=0))
		
		# OPTIONS
		temp_path = fpath(); temp_path.filename = filename
		# 1. fehmn.files was passed - assume that the directory in which this file sits is the work directory
		if temp_path.filename == 'fehmn.files':
		
			if temp_path.absolute_to_file != os.getcwd():
				self.work_dir = temp_path.absolute_to_file
			
			wd = temp_path.absolute_to_file+slash
			inconfilename = None
			with open(filename) as f:
				for ln in f.readlines():
					if ln.startswith('rsti:'): 
						inconfilename = wd+ln.split('rsti:')[-1].strip()
					if ln.startswith('grida:'): 
						gridfilename = wd+ln.split('grida:')[-1].strip()
					if ln.startswith('gridf:'): 
						gridfilename = wd+ln.split('gridf:')[-1].strip()
					if ln.startswith('input:'): 
						filename = wd+ln.split('input:')[-1].strip()
					if ln.startswith('stor:'): 
						storfilename = wd+ln.split('stor:')[-1].strip()
						self.files.stor = storfilename
			
			# set up  path objects then pass to read function
			self._path.filename = filename
			self.grid._path.filename = gridfilename
			if inconfilename:
				self.incon._path.inconfilename
			self.read(full_connectivity=full_connectivity,skip=skip)
			
		# 2. nothing passed - no path objects to set up, no reading required
		elif not filename and not gridfilename and not inconfilename:
			return
			
		# 3. input and grid file passed
		elif filename and gridfilename and not inconfilename:
			self._path.filename = filename
			self.grid._path.filename = gridfilename
			self.read(full_connectivity=full_connectivity,skip=skip)
			
		# 4. all passed
		elif filename and gridfilename and inconfilename:
			self._path.filename = filename
			self.grid._path.filename = gridfilename
			self.incon._path.filename = inconfilename
			self.read(full_connectivity=full_connectivity,skip=skip)
		
		else:
			print 'ERROR: file configuration not recognized'; return
	def __repr__(self): return self.filename			#Print out details
	def read(self,filename='',gridfilename='',inconfilename='',full_connectivity=dflt.full_connectivity,skip=[]):			#Reads data from file.
		'''Read FEHM input file and construct fdata object.
		
		:param filename: Name of FEHM input file. Alternatively, supplying 'fehmn.files' will cause PyFEHM to query this file for input, grid and restart file names if they are available.
		:type filename: str
		:param gridfilename: Name of FEHM grid file.
		:type gridfilename: str
		:param inconfilename: Name of FEHM restart file.
		:type inconfilename: str
		:param skip: List of macro strings to ignore when reading an input file.
		:type skip: list
		
		'''
		
		# set up paths
		if filename: self._path.filename = filename
		if gridfilename: self.grid._path.filename = filename
		if inconfilename: self.incon._path.filename = filename
		
		# THERE WILL ALWAYS BE A GRID PATH TO READ - INPUT FILES CANNOT BE READ WITHOUT A GRID
		self.grid.read(self.grid._path.full_path,full_connectivity=full_connectivity)
		self.files.grid = self.grid._path.full_path
		
		if self.incon._path.filename:
			self.incon.read(self.incon._path.full_path)
			self.files.incon = self.incon._path.full_path
			self.files._use_incon = True
			if len(self.incon.P) != self.grid.number_nodes: 
				print 'ERROR: grid and incon files contain different numbers of nodes'
				self.incon = fincon() 	# empty incon
				self.files.incon = ''	
				self.files._use_incon = False
			else: self._associate_incon()
		
		self.files.input = self._path.full_path
			
		
		#if gridfilename and (self.grid.number_nodes==0):
		#	print 'reading grid file'
		#	#self.gridfilename=gridfilename
		#	self.grid.read(gridfilename,full_connectivity=full_connectivity)
		#if inconfilename:
		#	print 'reading incon file'
		#	self.inconfilename=inconfilename
		#	if isinstance(inconfilename,str):
		#		#self.incon.read(inconfilename)
		#		#self.incon._parent=self
		#		self.files.incon = inconfilename
		#if filename: self._path.filename=filename; self.files.input = filename
		print 'reading input file'
		#infile = open(filename,'r')
		infile = open(self._path.full_path,'r')
		read_fn=dict(zip(fdata_sections,
						[self._read_cont,self._read_macro,self._read_zonn,self._read_zonn,self._read_macro,
						 self._read_time,self._read_ctrl,self._read_iter,self._read_macro,self._read_macro,
						 self._read_boun,self._read_macro,self._read_strs,self._read_text,self._read_sol,
						self._read_nfinv,self._read_hist,self._read_histnode,self._read_carb,self._read_model,
						 self._read_macro,self._read_nobr,self._read_flxz,self._read_rlpm,self._read_macro,
						 self._read_trac,self._read_model,self._read_model,self._read_vapl,self._read_adif,
						 self._read_ngas,self._read_flxo]))
		self._sections=[]
		"""Need to first establish dimensionality of input file. Requires initial read through."""
		more = True
		while more:
			line=infile.readline()
			keyword=line[0:4].strip()
			if keyword=='ctrl':
				self._read_ctrl(infile)
				more = False				
		infile.close()
		infile = open(self._path.full_path,'r')
		more = True
		precedingKey='start'
		precedingZoneKey = None
		line=infile.readline()
		while more:
			keyword=line[0:4].strip()
			#print keyword
			if keyword in fdata_sections and keyword not in skip:
				print 'reading '+keyword
				fn=read_fn[keyword]
				if keyword in macro_list.keys():
					self._read_macro(infile,keyword)
					precedingZoneKey = None
				elif keyword in model_list.keys():
					self._read_model(infile,keyword)
					precedingZoneKey = None
				else:
					if keyword in ['zone','zonn']:
						block = fn(infile)
						precedingZoneKey = copy(precedingKey)
					else:
						fn(infile)
						precedingZoneKey = None
				self._sections.append(keyword)
				precedingKey = keyword
			elif keyword[0:3] in fdata_sections and keyword not in skip:
				keyword = keyword[0:3]
				print 'reading '+keyword
				fn=read_fn[keyword]
				fn(infile)
				self._sections.append(keyword)
				precedingKey = keyword
			elif line.startswith('stop'): more=False; continue
			else: 
				#print line
				# start recording a code block
				foundKey = False
				if not precedingZoneKey: block = []
				else: precedingKey = precedingZoneKey
				while not foundKey:	
					block.append(line)
					line=infile.readline()
					keyword=line[0:4].strip()
					if keyword in fdata_sections and keyword not in skip: 
						foundKey = True
						continue
					elif keyword[0:3] in fdata_sections and keyword not in skip:
						foundKey = True
						continue
					elif line.startswith('stop'):
						foundKey = True
						continue
				#print precedingKey
				#print block
				self._unparsed_blocks.update(dict(((precedingKey,block),)))
				continue
			line=infile.readline()
		infile.close()
		self._add_boundary_zones()
		return self
	def write(self,filename='',writeSubFiles = True):	#Writes data to a file.
		'''Write fdata object to FEHM input file.
		
		:param filename: Name of FEHM input file to write to.
		:type filename: str
		:param writeSubFiles: Boolean indicating whether macro and zone information, designated as contained within other input files, should be written out, regardless of its existence. Non-existant files will always be written out.
		:type writeSubFiles: bool
		'''
		if writeSubFiles: self._writeSubFiles = writeSubFiles
		if filename: self._path.filename=filename
		if not self._path.filename: self._path.filename='default_INPUT.dat'
		out_flag = self._write_prep()
		if out_flag: return
		
		# ensure directory is created
		if self.work_dir: wd = self.work_dir
		else: wd = self._path.absolute_to_file
		try:
			os.makedirs(wd)
		except:
			pass
		# open file
		outfile = open(wd+slash+self._path.filename,'w')
			
		#if slash in self.filename:
		#	make_directory(self.filename)
		#if self.work_dir:
		#	if not os.path.isdir(self.work_dir): os.makedirs(self.work_dir)			
		#outfile = open(self.work_dir+self.filename,'w')
		outfile.write('# '+self.filename+'\n')
		self._write_unparsed(outfile,'start')
		if self.text: self._write_text(outfile); self._write_unparsed(outfile,'text')
		if self.sol: self._write_sol(outfile); self._write_unparsed(outfile,'sol')
		if self.nfinv: self._write_nfinv(outfile); self._write_unparsed(outfile,'nfinv')
		if self.nobr: self._write_nobr(outfile); self._write_unparsed(outfile,'nobr')
		if self.vapl: self._write_vapl(outfile); self._write_unparsed(outfile,'vapl')
		if self.adif != None: self._write_adif(outfile); self._write_unparsed(outfile,'adif')
		if self.flxo: self._write_flxo(outfile); self._write_unparsed(outfile,'flxo')
		if len(self.zone)>1 and not self.sticky_zones: 
			self._write_zonn_all(outfile)
			self._write_unparsed(outfile,'zone')
		if self.cont.variables: self._write_cont(outfile); self._write_unparsed(outfile,'cont')
		if self.hist.variables: self._write_hist(outfile); self._write_unparsed(outfile,'hist')
		if self.gradlist: self._write_macro(outfile,'grad'); self._write_unparsed(outfile,'grad')
		if self.pres: self._write_macro(outfile,'pres'); self._write_unparsed(outfile,'pres')
		if self.ngas.dof != None: self._write_ngas(outfile); self._write_unparsed(outfile,'ngas')
		if self.bounlist: self._write_boun(outfile); self._write_unparsed(outfile,'boun')
		if self.flow: self._write_macro(outfile,'flow'); self._write_unparsed(outfile,'flow')
		if self.hflx: self._write_macro(outfile,'hflx'); self._write_unparsed(outfile,'hflx')
		if self.perm: self._write_macro(outfile,'perm'); self._write_unparsed(outfile,'perm')
		if self.rock: self._write_macro(outfile,'rock'); self._write_unparsed(outfile,'rock')
		if self.pporlist: self._write_model(outfile,'ppor'); self._write_unparsed(outfile,'ppor')
		if self.cond: self._write_macro(outfile,'cond'); self._write_unparsed(outfile,'cond')
		if self.vconlist: self._write_model(outfile,'vcon'); self._write_unparsed(outfile,'vcon')
		if self.rlplist: self._write_model(outfile,'rlp'); self._write_unparsed(outfile,'rlp')		
		if self.rlpmlist: self._write_rlpm(outfile); self._write_unparsed(outfile,'rlpm')		
		if self.time: self._write_time(outfile); self._write_unparsed(outfile,'time')
		if self.ctrl: self._write_ctrl(outfile); self._write_unparsed(outfile,'ctrl')
		if self.iter: self._write_iter(outfile); self._write_unparsed(outfile,'iter')
		if self.carb.iprtype!=1: self._write_carb(outfile); self._write_unparsed(outfile,'carb')
		if self.strs.param['ISTRS']: self._write_strs(outfile); self._write_unparsed(outfile,'strs')
		if self.trac._on: self._write_trac(outfile); self._write_unparsed(outfile,'trac')
		outfile.write('stop\n')
		outfile.close()
	def add(self,obj,overwrite=False):									#Adds a new object to the file
		'''Attach a zone, boundary condition or macro object to the data file.
		
		:param obj: Object to be added to the data file.
		:type obj: fzone, fmacro, fmodel, fboun
		:param overwrite: Flag to overwrite macro if already exists for a particular zone.
		:type overwrite: bool
		'''
		if isinstance(obj,fmacro): self._add_macro(obj,overwrite)
		if isinstance(obj,fmodel): self._add_model(obj)
		elif isinstance(obj,fzone): self._add_zone(obj,overwrite)
		elif isinstance(obj,fboun): self._add_boun(obj)
		elif isinstance(obj,frlpm): self._add_rlpm(obj)
		elif isinstance(obj,frlpm_table): self._add_rlpm(obj)
	def delete(self,obj): 								#Deletes an object from the file
		'''Delete a zone, boundary condition or macro object from the data file.
		
		:param obj: Object to be deleted from the data file. Can be a list of objects.
		:type obj: fzone, fmacro, fmodel, fboun, list
		'''
		if isinstance(obj,fmacro): self._delete_macro(obj)
		if isinstance(obj,fmodel): self._delete_model(obj)
		elif isinstance(obj,fzone): self._delete_zone(obj)
		elif isinstance(obj,fboun): self._delete_boun(obj)
		elif isinstance(obj,frlpm): self._delete_rlpm(obj)
		elif isinstance(obj,frlpm_table): self._delete_rlpm(obj)
		elif isinstance(obj,list):
			for obji in copy(obj):
				if isinstance(obji,fmacro): self._delete_macro(obji)
				if isinstance(obji,fmodel): self._delete_model(obji)
				elif isinstance(obji,fzone): self._delete_zone(obji)
				elif isinstance(obji,fboun): self._delete_boun(obji)
				elif isinstance(obji,frlpm): self._delete_rlpm(obji)
				elif isinstance(obji,frlpm_table): self._delete_rlpm(obji)
	def _add_boundary_zones(self): 						#Automatically creates zones corresponding to x,y,z boundaries
		x0,x1 = self.grid.xmin,self.grid.xmax
		y0,y1 = self.grid.ymin,self.grid.ymax
		x = np.sort(np.unique([nd.position[0] for nd in self.grid.nodelist]))
		y = np.sort(np.unique([nd.position[1] for nd in self.grid.nodelist]))
		if self.grid.dimensions == 2:
			ks = [999,998,997,996,'XMIN','XMAX','YMIN','YMAX']
			for k in ks:
				if k in self.zone.keys(): self.delete(self.zone[k])
			
			dx = (x[1]-x[0])/2.
			zn = fzone(999,name='XMIN'); zn.rect([x0-0.1,y0-0.1],[x0+dx,y1+0.1])
			self.add(zn,overwrite=True)
			dx = (x[-1]-x[-2])/2.
			zn = fzone(998,name='XMAX'); zn.rect([x1-dx,y0-0.1],[x1+0.1,y1+0.1])
			self.add(zn,overwrite=True)
			
			dy = (y[1]-y[0])/2.
			zn = fzone(997,name='YMIN'); zn.rect([x0-0.1,y0-0.1],[x1+0.1,y0+dy])
			self.add(zn,overwrite=True)
			dy = (y[-1]-y[-2])/2.
			zn = fzone(996,name='YMAX'); zn.rect([x0-0.1,y1-dy],[x1+0.1,y1+0.1])
			self.add(zn,overwrite=True)
			
		elif self.grid.dimensions == 3:
			z0,z1 = self.grid.zmin,self.grid.zmax
			z = np.sort(np.unique([nd.position[2] for nd in self.grid.nodelist]))
			
			ks = [999,998,997,996,995,994,'XMIN','XMAX','YMIN','YMAX','ZMIN','ZMAX']
			for k in ks:
				if k in self.zone.keys(): self.delete(self.zone[k])
			
			dx = (x[1]-x[0])/2.
			zn = fzone(999,name='XMIN'); zn.rect([x0-0.1,y0-0.1,z0-0.1],[x0+dx,y1+0.1,z1+0.1])
			self.add(zn,overwrite=True)
			
			dx = (x[-1]-x[-2])/2.
			zn = fzone(998,name='XMAX'); zn.rect([x1-dx,y0-0.1,z0-0.1],[x1+0.1,y1+0.1,z1+0.1])
			self.add(zn,overwrite=True)
			
			dy = (y[1]-y[0])/2.
			zn = fzone(997,name='YMIN'); zn.rect([x0-0.1,y0-0.1,z0-0.1],[x1+0.1,y0+dy,z1+0.1])
			self.add(zn,overwrite=True)
			
			dy = (y[-1]-y[-2])/2.
			zn = fzone(996,name='YMAX'); zn.rect([x0-0.1,y1-dy,z0-0.1],[x1+0.1,y1+0.1,z1+0.1])
			self.add(zn,overwrite=True)
			
			dz = (z[1]-z[0])/2.
			zn = fzone(995,name='ZMIN'); zn.rect([x0-0.1,y0-0.1,z0-0.1],[x1+0.1,y1+0.1,z0+dz])
			self.add(zn,overwrite=True)
			
			dz = (z[-1]-z[-2])/2.
			zn = fzone(994,name='ZMAX'); zn.rect([x0-0.1,y0-0.1,z1-dz],[x1+0.1,y1+0.1,z1+0.1])
			self.add(zn,overwrite=True)
			
		else:
			print 'Unrecognized grid dimensionality'
	def _associate_incon(self):							#Associates initial condition data with nodes
		if not self._associate: return
		names = ('T','P','S','S_co2l','S_co2g','co2aq')
		vars = [self.incon.T,self.incon.P,self.incon.S,self.incon.S_co2l,
			self.incon.S_co2g,self.incon.co2aq]
			
		names = [name for name,var in zip(names,vars) if isinstance(var,np.ndarray)]
		if not self._running: names = [name+'i' for name in names]
		vars = np.array([var for var in vars if isinstance(var,np.ndarray)])
		
		for nd,var in zip(self.grid.nodelist,vars.T):
			for i,name in enumerate(names):
				nd.__setattr__('_'+name,var[i])
				
		names = ['strs','disp']
		strs2D = False; strs3D = False
		if isinstance(self.incon.strs_xx,np.ndarray):
			if isinstance(self.incon.strs_zz,np.ndarray): strs3D = True
			else: strs2D = True
			
		for i,nd in enumerate(self.grid.nodelist):
			if self._running:
				if strs2D: nd._strs = [self.incon.strs_xx[i],self.incon.strs_yy[i],self.incon.strs_xy[i]]
				elif strs3D: nd._strs = [self.incon.strs_xx[i],self.incon.strs_yy[i],self.incon.strs_zz[i],self.incon.strs_xy[i],self.incon.strs_yz[i],self.incon.strs_xz[i]]
				if strs2D: nd._disp = [self.incon.disp_x[i],self.incon.disp_y[i]]
				elif strs3D: nd._disp = [self.incon.disp_x[i],self.incon.disp_y[i],self.incon.disp_z[i]]
			else:
				if strs2D: nd._strsi = [self.incon.strs_xx[i],self.incon.strs_yy[i],self.incon.strs_xy[i]]
				elif strs3D: nd._strsi = [self.incon.strs_xx[i],self.incon.strs_yy[i],self.incon.strs_zz[i],self.incon.strs_xy[i],self.incon.strs_yz[i],self.incon.strs_xz[i]]
				if strs2D: nd._dispi = [self.incon.disp_x[i],self.incon.disp_y[i]]
				elif strs3D: nd._dispi = [self.incon.disp_x[i],self.incon.disp_y[i],self.incon.disp_z[i]]
	def _write_unparsed(self,outfile,key):
		if not self.keep_unknown: return
		if key in self._unparsed_blocks.keys():
			block = self._unparsed_blocks[key]
			for line in block:
				if key == 'start': line = '# '+line
				outfile.write(line)
	def _read_adif(self,infile):							#ADIF: Reads ADIF macro.
		line = infile.readline().strip().split()
		self.adif = float(line[0])
		if self.adif in [333.,666.]: self.adif = int(self.adif)
	def _write_adif(self,outfile):								#Writes ADIF macro.
		if self.adif:
			outfile.write('adif\n')
			outfile.write(str(self.adif)+'\n')
	def _read_boun(self,infile):							#BOUN: Reads BOUN macro.
		line=infile.readline().strip()	
		new_bouns=[]
		file_flag=False
		# read models
		while not (not line or line.startswith('end')):
			if line.startswith('file'): file_flag = True; break 		# read file data	
			new_boun = fboun()
			line=infile.readline().strip()
			new_boun.type = line
			line=infile.readline().strip()
			nums = line.split()
			new_boun.times = [float(num) for num in nums[1:]]
			line=infile.readline().strip() 			# read next model
			while not (line.startswith('model') or not line or line.startswith('end')):
				var = [line,]
				line=infile.readline().strip()
				nums = line.split()
				for num in nums: var.append(float(num))
				new_boun.variable.append(var)
				line=infile.readline().strip() 			# read next model
			new_bouns.append(new_boun)
		
		if file_flag:
			line=infile.readline().strip()
			if not os.path.isfile(line):
				# check if in subdirectory with input file
				fname = self.filename.split(slash)
				if len(fname)>0:
					fn0 = ''
					for fn in fname[:-1]: fn0 += fn
					if not os.path.isfile(fn0+slash+line):
						print 'ERROR: cannot find macro file '+line
					else:
						macrofile = open(fn0+slash+line)
						line = macrofile.readline().strip()
						self._read_boun(macrofile)
						macrofile.close()
			else:
				macrofile = open(line)
				line = macrofile.readline().strip()
				self._read_boun(macrofile)
				macrofile.close()
		else:
			# read zone assignments
			line=infile.readline().strip() 			# read next zone assignment
			while line:
				nums = line.split()
				if (nums[0] == '1' and nums[1] == '0' and nums[2] == '0') or (int(nums[0])<0):
					new_bouns[int(nums[-1])-1].zone.append(self.zone[_zone_ind(nums[0])])
				else:
					nds = (int(nums[0]),int(nums[1]),int(nums[2]))
					new_bouns[int(nums[-1])-1].zone.append(nds)
				line=infile.readline().strip() 			# read next zone assignment
			for new_boun in new_bouns:
				self._add_boun(new_boun)
	def _write_boun(self,outfile):								#Writes BOUN macro.
		ws = _title_string('BOUNDARY CONDITIONS',72)
		outfile.write(ws)
		#if self.sticky_zones:
		#	self._write_zonn_one(outfile,[bm.zone for bm in self.bounlist if bm.zone.index != 0])
		if self.sticky_zones:	
			allzns = []
			for bm in self.bounlist:
				for zn in bm.zone:
					if zn.index != 0: allzns.append(zn)
			self._write_zonn_one(outfile,allzns)
		outfile.write('boun\n')
		nm = 1
		for boun in self.bounlist:
			outfile.write('model '+str(nm)+'\n')
			nm+=1
			outfile.write(boun.type + '\n')
			outfile.write(str(boun.n_times)+'\t')
			cnt = 0
			for t in boun.times:
				outfile.write(str(t)+'\t')
				cnt +=1
				if cnt == 10: outfile.write('\n'); cnt = 0
			if cnt != 0: outfile.write('\n')
			#outfile.write('\n')
			for var in boun.variable:
				outfile.write(var[0]+'\n')
				cnt = 0
				for v in var[1:]:
					outfile.write(str(v)+'\t')
					cnt +=1
					if cnt == 10: outfile.write('\n'); cnt = 0
				if cnt != 0: outfile.write('\n')
				#outfile.write('\n')
		outfile.write('end\n')
		nm = 1
		for boun in self.bounlist:
			if not boun.zone: nm+=1; continue
			for zone in boun.zone:
				if isinstance(zone,fzone):
					ind = zone.index
					if not ind: outfile.write(str(1)+'\t'+'0\t0\t')
					else: outfile.write(str(-ind)+'\t'+'0\t0\t')
					outfile.write(str(nm)+'\n')
				else:
					outfile.write(str(zone[0])+'\t'+str(zone[1])+'\t'+str(zone[2])+'\t')
					outfile.write(str(nm)+'\n')
			nm+=1
		outfile.write('\n')
	def _add_boun(self,boun=fboun()):							#Adds a BOUN model.
		boun._parent = self
		if isinstance(boun.zone,(int,tuple)): boun.zone = [boun.zone]
		zns = []
		for zn in boun.zone:
			if isinstance(zn,tuple): 
				zns.append(tuple([int(ls) for ls in zn]))
			elif isinstance(zn,int) or isinstance(zn,str):
				if zn in self.zone.keys(): zns.append(self.zone[zn])
			elif isinstance(zn,fzone):
				zns.append(zn)
		boun.zone = zns
		self._bounlist.append(boun)
	def _delete_boun(self,boun=fboun()):
		self._bounlist.remove(boun)
	def _read_carb(self,infile):							#CARB: Reads CARB and associated macros.
		from copy import deepcopy
		line=infile.readline().strip()
		nums = line.split()
		self.carb.iprtype = int(nums[0])
		line=infile.readline().strip()
		while not (line.startswith('endcarb') or line.startswith('end carb')):
			if line.startswith('brine'):
				self.carb.brine = 1
			elif line.startswith('co2frac'):
				self._read_macro(infile,'co2frac')
			elif line.startswith('co2flow'):
				self._read_macro(infile,'co2flow')
			elif line.startswith('co2pres'):
				self._read_macro(infile,'co2pres')
			elif line.startswith('co2diff'):
				self._read_macro(infile,'co2diff')
			line=infile.readline().strip()
	def _write_carb(self,outfile):								#Writes CARB and associated macros.
		ws = _title_string('CO2 MODULE',72)
		outfile.write(ws)
		outfile.write('restart\n\n')
		if self.sticky_zones:
			zns = []
			for key in ['co2frac','co2flow','co2pres','co2diff']:
				zns += [m.zone for m in self._allMacro[key] if m.zone.index]
			self._write_zonn_one(outfile,list(set(zns)))
		outfile.write('carb\n')
		outfile.write(str(self.carb.iprtype)+'\n')
		sz = copy(self.sticky_zones)
		self.sticky_zones = False
		if self.co2fraclist: self._write_macro(outfile,'co2frac')
		if self.co2flowlist: self._write_macro(outfile,'co2flow')
		if self.co2preslist: self._write_macro(outfile,'co2pres')
		if self.co2difflist: self._write_macro(outfile,'co2diff')
		if self.carb.brine: outfile.write('brine\n')
		self.sticky_zones = copy(sz)
		outfile.write('endcarb\n')
	def _read_cont(self,infile):							#CONT: Reads CONT macro.
		line=infile.readline().strip()
		nums = line.split()
		for i in range(4-len(nums)): nums.append(None)
		self._cont = fcont()
		if nums[0] in ['avs','avsx','fehm','free','surf','tec','sur']:
			self.cont.type=nums[0]
			self.cont.timestep_interval=int(float(nums[1]))
			self.cont.time_interval=float(nums[2])
			if nums[3] == None: self.cont.time_flag=False
			else: self.cont.time_flag=True
			
		line=infile.readline().strip()
		while not line.startswith('end'):
			gotVar = False
			if line.startswith('zone'):
				line=infile.readline().strip()
				nums = line.split()
				num_zones = int(float(nums[0]))
				moreZones = True
				while moreZones:
					line=infile.readline().strip()
					nums = line.split()
					for num in nums: self.cont.zones.append(self.zone[int(num)])
					if len(self.cont.zones) == num_zones: moreZones=False; line=infile.readline().strip()
			for vars,ln in zip(contour_variables,[4,3,2,1]):
				for var in vars:
					if line[:ln]==var[:ln]:
						gotVar = True
						self.cont.variables.append([var])
					if gotVar: break
				if gotVar: break			
			line=infile.readline().strip()
	def _write_cont(self,outfile):								#Writes CONT macro.
		ws = _title_string('CONTOUR OUTPUT REQUESTS',72)
		self.cont.variables = list(flatten(self.cont.variables))
		outfile.write(ws)
		outfile.write('cont\n')
		outfile.write(self.cont.type+'\t')
		outfile.write(str(self.cont.timestep_interval)+'\t')
		outfile.write(str(self.cont.time_interval)+'\t')
		if self.cont.time_flag: outfile.write('time\t')
		outfile.write('\n')
		if self.cont.zones:
			outfile.write('zone\n')
			outfile.write(str(len(self.cont.zones))+'\n')
			for zn in self.cont.zones: outfile.write(str(zn.index)+'\t')
			outfile.write('\n')
			
		# ensure list is unique
		vars = list(flatten(self.cont.variables))
		varsU = []
		for var in vars:
			if var not in varsU: varsU.append(var)
		self.cont.variables = varsU
		
		for var in self.cont.variables:
			outfile.write(var+'\n')
		outfile.write('end\n')
	def _read_ctrl(self,infile):							#CTRL: Reads CTRL macro.
		line=infile.readline().strip()
		nums = line.split()
		for i in range(5-len(nums)): nums.append(None)
		for num, param in zip(nums,['max_newton_iterations_MAXIT','newton_cycle_tolerance_EPM','number_orthogonalizations_NORTH','max_solver_iterations_MAXSOLVE','acceleration_method_ACCM']):
			if not num: self.ctrl[param] = num
			else:
				if param[-4:]=='ACCM':self.ctrl[param] = num
				else: self.ctrl[param] = float(num)
		line=infile.readline().strip()
		nums = line.split()
		for i in range(3-len(nums)): nums.append(None)
		for num, param in zip(nums,['JA','JB','JC','order_gauss_elim_NAR']):
			if not num: self.ctrl[param] = num
			else: self.ctrl[param] = int(num)
		line=infile.readline().strip()
		line=infile.readline().strip()
		nums = line.split()
		for i in range(3-len(nums)): nums.append(None)
		for num, param in zip(nums,['implicitness_factor_AAW','gravity_direction_AGRAV','upstream_weighting_UPWGT']):
			if not num: self.ctrl[param] = num
			else:
				if param[-5:]=='UPWGT':self.ctrl[param] = float(num)
				else: self.ctrl[param] = int(float(num))
		line=infile.readline().strip()
		nums = line.split()
		for i in range(4-len(nums)): nums.append(None)
		for num, param in zip(nums,['max_multiply_iterations_IAMM','timestep_multiplier_AIAA','min_timestep_DAYMIN','max_timestep_DAYMAX']):
			if not num: self.ctrl[param] = num
			else: self.ctrl[param] = float(num)
		line=infile.readline().strip()
		nums = line.split()
		for i in range(2-len(nums)): nums.append(None)
		for num, param in zip(nums,['geometry_ICNL','stor_file_LDA']):
			if not num: self.ctrl[param] = num
			else: self.ctrl[param] = int(num)		
		self.dtmin = self.ctrl['min_timestep_DAYMIN']
		self.dtmax = self.ctrl['max_timestep_DAYMAX']
		self.dtx = self.ctrl['timestep_multiplier_AIAA']
	def _write_ctrl(self,outfile):								#Writes CTRL macro.
		ws = _title_string('SIMULATION CONTROL PARAMETERS',72)
		outfile.write(ws)
		outfile.write('ctrl\n')
		if not self.ctrl['max_newton_iterations_MAXIT']==None: outfile.write(str(int(self.ctrl['max_newton_iterations_MAXIT']))+'\t')
		if not self.ctrl['newton_cycle_tolerance_EPM']==None: outfile.write(str(self.ctrl['newton_cycle_tolerance_EPM'])+'\t')
		if not self.ctrl['number_orthogonalizations_NORTH']==None: outfile.write(str(int(self.ctrl['number_orthogonalizations_NORTH']))+'\t')
		if not self.ctrl['max_solver_iterations_MAXSOLVE']==None: outfile.write(str(int(self.ctrl['max_solver_iterations_MAXSOLVE']))+'\t')
		if not self.ctrl['acceleration_method_ACCM']==None: outfile.write(str(self.ctrl['acceleration_method_ACCM'])+'\t')
		outfile.write('\n')
		if not self.ctrl['JA']==None: outfile.write(str(self.ctrl['JA'])+'\t')
		if not self.ctrl['JB']==None: outfile.write(str(self.ctrl['JB'])+'\t')
		if not self.ctrl['JC']==None: outfile.write(str(self.ctrl['JC'])+'\t')
		if not self.ctrl['order_gauss_elim_NAR']==None: outfile.write(str(self.ctrl['order_gauss_elim_NAR'])+'\t')
		outfile.write('\n')
		outfile.write('\n')
		if not self.ctrl['implicitness_factor_AAW']==None: outfile.write(str(self.ctrl['implicitness_factor_AAW'])+'\t')
		if not self.ctrl['gravity_direction_AGRAV']==None: outfile.write(str(self.ctrl['gravity_direction_AGRAV'])+'\t')
		if not self.ctrl['upstream_weighting_UPWGT']==None: outfile.write(str(self.ctrl['upstream_weighting_UPWGT'])+'\t')
		outfile.write('\n')
		if not self.ctrl['max_multiply_iterations_IAMM']==None: outfile.write(str(int(self.ctrl['max_multiply_iterations_IAMM']))+'\t')
		if not self.ctrl['timestep_multiplier_AIAA']==None: outfile.write(str(self.ctrl['timestep_multiplier_AIAA'])+'\t')
		if not self.ctrl['min_timestep_DAYMIN']==None: outfile.write(str(self.ctrl['min_timestep_DAYMIN'])+'\t')
		if not self.ctrl['max_timestep_DAYMAX']==None: outfile.write(str(self.ctrl['max_timestep_DAYMAX'])+'\t')
		outfile.write('\n')
		if not self.ctrl['geometry_ICNL']==None: outfile.write(str(self.ctrl['geometry_ICNL'])+'\t')
		if not self.ctrl['stor_file_LDA']==None: outfile.write(str(self.ctrl['stor_file_LDA'])+'\t')
		outfile.write('\n')
	def print_ctrl(self):										#Prints out variables contained in CTRL.
		'''Display contents of CTRL macro.
		'''
		for k in self.ctrl.keys():	print k +': ' + str(self.ctrl[k])
	def _read_hist(self,infile):							#HIST: Reads HIST macro.
		line=infile.readline().strip()
		nums = line.split()
		if len(nums)<2: nums.append(1)
		if len(nums)<3: nums.append(1e30)
		if nums[0] in ['csv','surf','tec']:
			self.hist.type=nums[0]
			self.hist.timestep_interval=int(nums[1])
			self.hist.time_interval=float(nums[2])			
			line=infile.readline().strip()
		while not line.startswith('end'):
			gotVar = False
			for var in history_variables:
				if line.startswith(var):
					self.hist.variables.append([var])
					break
			line=infile.readline()		
	def _read_histnode(self,infile):							#Reads NODE macro.
		line=infile.readline().strip()
		nums = line.split()
		if nums[0].isdigit():
			node_num = int(nums[0])
			more = True
			newind = 0
			numXYZ = 0
			while more:
				line=infile.readline().strip()
				nums = line.split()
				for num in nums:
					if int(num)>0:
						self.hist.nodelist.append(self.grid.node[int(num)])
					else:
						numXYZ += 1
					newind += 1
				if newind == node_num: more = False
			for i in range(numXYZ):
				line=infile.readline().strip()
				nums = line.split()
				self.hist.nodelist.append(self.grid.node_nearest_point([float(num) for num in nums]))	
		else:
			more = True
			while more:
				line=infile.readline().strip()
				if not line: more = False; continue
				nums = line.split()
				nums_zone,nums_params = nums[:3],nums[3:]
				self.hist.zonelist.append(self._macro_zone(nums_zone))
	def _read_flxz(self,infile):								#Reads ZFLX macro.
		line=infile.readline().strip()
#		self._hist = fhist()
		nums = line.split()
		
		node_num = int(nums[0])
		more = True
		newind = 0
		numXYZ = 0
		while more:
			line=infile.readline().strip()
			nums = line.split()
			for num in nums:
				if self.zone.has_key(int(num)):
					self.hist.zoneflux.append(self.zone[int(num)])
				else:
					self.hist.zoneflux.append(int(num))
					print 'WARNING: zone ' +num+' in FLXZ not defined.'
				newind += 1
			if newind == node_num: more = False
	def _write_hist(self,outfile):								#Writes HIST macro.
		if not self.hist.nodelist and not self.hist.zonelist and not self.hist.zoneflux: print 'WARNING: no zones or nodes specified for history output'; return
#		if self.hist.nodelist and self.hist.zonelist: print 'WARNING: not set up to print both hist nodes and hist zones'; return
		if not self.hist.variables: print 'WARNING: no variables requested in hist'
		ws = _title_string('HISTORY OUTPUT REQUESTS',72)
		outfile.write(ws)
		
		# ensure list is unique
		vars = list(flatten(self.hist.variables))
		varsU = []
		for var in vars:
			if var not in varsU: varsU.append(var)
		self.hist.variables = varsU
			
		znlist = []	
		if self.hist.zoneflux:
			self.hist.zoneflux = list(flatten(self.hist.zoneflux))			
			zns = [] 		# convert names and indices to zone objects
			for zn in self.hist.zoneflux:
				if isinstance(zn,int) or isinstance(zn,str): zns.append(self.zone[zn])
				elif isinstance(zn,fzone): zns.append(zn)
			self.hist.zoneflux = zns
			zns = []; znsInds = []		# remove duplicate zones
			for zn in self.hist.zoneflux:
				if zn.index in znsInds: continue
				zns.append(zn); znsInds.append(zn.index)
			self.hist.zoneflux = zns				
			self._write_zonn_one(outfile,self.hist.zoneflux)
			outfile.write('flxz\n')
			outfile.write(str(len(self.hist.zoneflux))+'\n')
			cnt = 0
			for zn in self.hist.zoneflux:
				outfile.write(str(zn.index)+'\t')
				cnt += 1
				if cnt == 10: outfile.write('\n'); cnt = 0
			if cnt != 0: outfile.write('\n')

		self._write_unparsed(outfile,'flxz')	
		
		znlist = []		
		if self.hist.zonelist: 
			zns = []
			for zn in self.hist.zonelist:
				if isinstance(zn,int) or isinstance(zn,str): zns.append(self.zone[zn])
				elif isinstance(zn,fzone): zns.append(zn)
			self._write_zonn_one(outfile,zns)
			outfile.write('node\n')
			outfile.write('block\n')
			for zn in zns:
				if isinstance(zn,int) or isinstance(zn,str): zn = self.zone[zn]
				if isinstance(zn,tuple):
					outfile.write(str(zn[0])+'\t'+str(zn[1])+'\t'+str(zn[2])+'\t')
				else:
					if not zn.index: outfile.write(str(1)+'\t'+'0\t0\t')
					else: outfile.write(str(-zn.index)+'\t'+'0\t0\t') 
				outfile.write('\n')
			outfile.write('\n')
			
		self._write_unparsed(outfile,'node')	
		
		if self.hist.nodelist:
			self.hist.nodelist = list(flatten(self.hist.nodelist))
			nds = []; ndsInds = []
			for nd in self.hist.nodelist:
				if isinstance(nd,int):
					if nd not in ndsInds:
						nds.append(self.grid.node[nd])
						ndsInds.append(nd)
				elif isinstance(nd,fnode):
					if nd.index not in ndsInds:
						nds.append(nd)
						ndsInds.append(nd.index)
			self.hist.nodelist = nds
			outfile.write('node\n')
			outfile.write(str(len(self.hist.nodelist))+'\n')
			cnt = 0
			for nd in self.hist.nodelist:
				outfile.write(str(nd.index)+'\t')
				cnt += 1
				if cnt == 10: outfile.write('\n'); cnt = 0
			if cnt != 0: outfile.write('\n')
		outfile.write('hist\n')
		if self.hist.type:
			outfile.write(self.hist.type+'\t')
			outfile.write(str(self.hist.timestep_interval)+'\t')
			outfile.write(str(self.hist.time_interval)+'\t')
			outfile.write('\n')
		vars = list(flatten(self.hist.variables))
		for var in vars:
			outfile.write(var+'\n')
		outfile.write('end\n')
	def _read_flxo(self,infile): 							#FLXO: Reads FLXO macro.
		line=infile.readline().strip()
		nums = line.split()
		if nums[0].isdigit():
			node_num = int(nums[0])*2
			more = True
			newind = 0
			numXYZ = 0
			nds = []
			ndsXYZ = []
			while more:
				line=infile.readline().strip()
				nums = line.split()
				for num in nums:
					nds.append(int(num))
					if int(num)<0:
						numXYZ += 1
					newind += 1
				if newind == node_num: more = False
			for i in range(numXYZ):
				line=infile.readline().strip()
				nums = line.split()
				self.grid.node_nearest_point([float(num) for num in nums])
				nds[np.where(nds<0)[0][0]] = self.grid.node_nearest_point([float(num) for num in nums]).index
			nds = [self.grid.node[nd] for nd in nds]
			for i1,i2 in zip(range(0,node_num,2),range(0,node_num,2)):
				self.flxo.append((nds[i1],nds[i2]))
	def _write_flxo(self,outfile):								#Writes FLXO macro.
		outfile.write('flxo\n')
		outfile.write(str(len(self.flxo))+'\n')
		for nd1,nd2 in self.flxo:
			if isinstance(nd1,fnode): nd1 = nd1.index
			if isinstance(nd2,fnode): nd2 = nd2.index
			outfile.write(str(nd1)+'\t'+str(nd2)+'\n') 
	def _read_iter(self,infile):							#ITER: Reads ITER macro.
		line=infile.readline().strip()
		nums = line.split()
		for i in range(5-len(nums)): nums.append(None)
		for num, param in zip(nums,['linear_converge_NRmult_G1','quadratic_converge_NRmult_G2','stop_criteria_NRmult_G3','machine_tolerance_TMCH','overrelaxation_factor_OVERF']):
			if not num: self.iter[param] = num
			else: self.iter[param] = float(num)
		line=infile.readline().strip()	
		nums = line.split()
		for i in range(5-len(nums)): nums.append(None)
		for num, param in zip(nums,['reduced_dof_IRDOF','reordering_param_ISLORD','IRDOF_param_IBACK','number_SOR_iterations_ICOUPL','max_machine_time_RNMAX']):
			if not num: self.iter[param] = num
			else: 
				if not param.endswith('RNMAX'): self.iter[param] = int(num)
				else: self.iter[param] = float(num)
	def _write_iter(self,outfile):								#Writes ITER macro.
		ws = _title_string('SOLVER PARAMETERS',72)
		outfile.write(ws)
		outfile.write('iter\n')
		if not self.iter['linear_converge_NRmult_G1']==None: outfile.write(str(self.iter['linear_converge_NRmult_G1'])+'\t')
		if not self.iter['quadratic_converge_NRmult_G2']==None: outfile.write(str(self.iter['quadratic_converge_NRmult_G2'])+'\t')
		if not self.iter['stop_criteria_NRmult_G3']==None: outfile.write(str(self.iter['stop_criteria_NRmult_G3'])+'\t')
		if not self.iter['machine_tolerance_TMCH']==None: outfile.write(str(self.iter['machine_tolerance_TMCH'])+'\t')
		if not self.iter['overrelaxation_factor_OVERF']==None: outfile.write(str(self.iter['overrelaxation_factor_OVERF'])+'\t')
		outfile.write('\n')
		if not self.iter['reduced_dof_IRDOF']==None: outfile.write(str(self.iter['reduced_dof_IRDOF'])+'\t')
		if not self.iter['reordering_param_ISLORD']==None: outfile.write(str(self.iter['reordering_param_ISLORD'])+'\t')
		if not self.iter['IRDOF_param_IBACK']==None: outfile.write(str(self.iter['IRDOF_param_IBACK'])+'\t')
		if not self.iter['number_SOR_iterations_ICOUPL']==None: outfile.write(str(self.iter['number_SOR_iterations_ICOUPL'])+'\t')
		if not self.iter['max_machine_time_RNMAX']==None: outfile.write(str(self.iter['max_machine_time_RNMAX'])+'\t')
		outfile.write('\n')
	def print_iter(self):										#Prints out variables contained in ITER.
		'''Display contents of ITER macro.
		'''
		for k in self.iter.keys():	print k +': ' + str(self.iter[k])
	def _read_nfinv(self,infile):							#NFINV: Reads NFINV macro.
		self.nfinv=True
	def _write_nfinv(self,outfile):								#Writes NFINV macro.
		if self.nfinv:
			outfile.write('nfinv\n')
	def _read_nobr(self,infile):							#NOBR: Reads NOBR macro.
		self.nobr=True
	def _write_nobr(self,outfile):								#Writes NOBR macro.
		if self.nobr:
			outfile.write('nobr\n')
	def _read_rlpm(self,infile):							#RLPM: Reads RLPM macro.		
		moreGroups=True
		line=infile.readline().strip().split()
		# first read the models
		rlpms = []
		while moreGroups:		
			group = line[1]
			moreModels = True
			relperms = []; capillarys = []
			while moreModels:
				line=infile.readline().strip().split()
				if not line: moreModels=False;moreGroups=False; continue	
				elif line[0].startswith('end'): moreModels=False;moreGroups=False; continue	
				if line[0]=='group': moreModels=False; continue	
				if line[0] in rlpm_phases: relperms.append([line[0],line[1],line[2:]])
				elif '/' in line[1]: capillarys.append([tuple(line[1].split('/')),rlpm_cap2[line[2]],line[3:]])
			newrlpm = frlpm(group=group,relperm=relperms,capillary=capillarys)
			rlpms.append(newrlpm)
		rlpms = dict([(rlpm.group,rlpm) for rlpm in rlpms])
		# next read the zones
		moreZones=True
		while moreZones:
			line=infile.readline().strip().split()
			if not line: moreZones=False; continue
			rlpms[line[-1]].zone = self._macro_zone(line[:3])
		self._rlpmlist = rlpms.values()			
	def _write_rlpm(self,outfile):								#Writes RLPM macro.
		ws = _title_string(macro_titles['rlpm'],72)
		outfile.write(ws)		
		if self.sticky_zones:
				allzns = []
				for bm in self.rlpmlist:
					if isinstance(bm.zone,fzone): bm.zone = [bm.zone,]	
					for zn in bm.zone:
						if zn.index != 0: allzns.append(zn)
				self._write_zonn_one(outfile,allzns)				
		outfile.write('rlpm\n')
		self._rlpmlist.sort(key=lambda x: x.group)
		table_number = 1
		for rlpm in self._rlpmlist:
			if isinstance(rlpm,frlpm):
				outfile.write('group '+str(int(rlpm.group))+'\n')
				for relperm in rlpm.relperm.values():
					outfile.write(relperm.phase+'\t')
					outfile.write(relperm.type+'\t')
					for k in rlpm_dicts[relperm.type]:
						outfile.write(str(relperm.param[k[0]])+'\t')
					outfile.write('\n')
				for capillary in rlpm.capillary.values():
					outfile.write('cap\t')
					outfile.write(capillary.phase[0]+'/'+capillary.phase[1]+'\t')
					outfile.write(rlpm_cap1[capillary.type]+'\t')
					for k in rlpm_dicts[capillary.type]:
						outfile.write(str(capillary.param[k[0]])+'\t')
					outfile.write('\n')
				#outfile.write('\n')
			elif isinstance(rlpm,frlpm_table):
				outfile.write('group '+str(int(rlpm.group))+'\n')
				# table number
				outfile.write('table\t'+str(table_number)+'\t')
				table_number +=1
				# table width
				wid = 3
				if len(rlpm.capillary)>0: wid = 4
				outfile.write(str(wid)+'\t'+rlpm.phase1[0]+'\t'+rlpm.phase2[0]+'\t')
				if wid == 4:
					outfile.write(rlpm.phase1[0]+'/'+rlpm.phase2[0])
				outfile.write('\n')
				if wid == 3:
					for s, ph1,ph2 in zip(rlpm.saturation,rlpm.phase1[1],rlpm.phase2[1]):
						outfile.write(str(s)+'\t'+str(ph1)+'\t'+str(ph2)+'\n')
				elif wid == 4:
					for s, ph1,ph2,cap in zip(rlpm.saturation,rlpm.phase1[1],rlpm.phase2[1],rlpm.capillary):
						outfile.write(str(s)+'\t'+str(ph1)+'\t'+str(ph2)+'\t'+str(cap)+'\n')
		outfile.write('\n')
		for rlpm in self._rlpmlist:
			for zone in rlpm.zone:
				if isinstance(zone,fzone):
					ind = zone.index
					if not ind: outfile.write(str(1)+'\t'+'0\t0\t')
					else: outfile.write(str(-ind)+'\t'+'0\t0\t')
					outfile.write(str(rlpm.group)+'\n')
				else:
					outfile.write(str(zone[0])+'\t'+str(zone[1])+'\t'+str(zone[2])+'\t')
					outfile.write(str(rlpm.group)+'\n')
		outfile.write('\n')
	def _add_rlpm(self,rlpm=frlpm()):							
		rlpm._parent = self
		if rlpm.group == None: 
			gps = [r.group for r in self._rlpmlist]
			for i in range(1,np.max(gps)+2):
				if i not in gps: rlpm.group = i; break
		self._rlpmlist.append(rlpm)
	def _delete_rlpm(self,rlpm=frlpm()):
		self._rlpmlist.remove(rlpm)
	def _read_sol(self,infile):								#SOL: Reads SOL macro.
		line=infile.readline().strip()
		nums = line.split()
		for i in range(2-len(nums)): nums.append(None)
		for num, param in zip(nums,['coupling_NTT','element_integration_INTG']):
			if not num: self.sol[param] = num
			else: self.sol[param] = int(num)
	def _write_sol(self,outfile):								#Writes SOL macro.
		ws = _title_string('SOLUTION TYPE',72)
		outfile.write(ws)
		outfile.write('sol\n')
		if not self.sol['coupling_NTT']==None: outfile.write(str(self.sol['coupling_NTT'])+'\t')
		if not self.sol['element_integration_INTG']==None: outfile.write(str(self.sol['element_integration_INTG'])+'\t')
		outfile.write('\n')
	def _read_strs(self,infile):							#STRS: Reads STRS and associated macros.
		from copy import deepcopy
		line=infile.readline().strip()
		nums = line.split()
		self.strs.param['ISTRS'] = int(nums[0])
		self.strs.param['IHMS'] = int(nums[1])
		line=infile.readline().strip()
		while not line.startswith('stressend'):
			if line.startswith('bodyforce'): 				# bodyforce boolean
				self.strs.bodyforce = 1
			elif line.startswith('initcalc'):				# initcalc boolean
				self.strs.initcalc = 1
			elif line.startswith('fem'):					# fem boolean
				self.strs.fem = 1		
			elif line.startswith('excess_she'): 			# reporting on excess shear stress?
				line=infile.readline().strip()
				nums = line.split()
				for i in range(3-len(nums)): nums.append(None)
				self.strs.excess_she['PAR1']=nums[0]
				self.strs.excess_she['PAR2']=nums[1]
				self.strs.excess_she['PAR3']=nums[2]
			elif line.startswith('permmodel'):				# read details of stress/permeability model
				self._read_model(infile,'permmodel')
			elif line.startswith('elastic'):
				self._read_macro(infile,'elastic')
			elif line.startswith('stressboun'):
				self._read_macro(infile,'stressboun')
			elif line.startswith('biot'):
				self._read_macro(infile,'biot')
			elif line.startswith('tolerance'):
				line = infile.readline().strip()
				nums = line.split()
				self.strs.tolerance = float(nums[0])
			elif line.startswith('zonn') or line.startswith('zone'):
				self._read_zonn(infile)
			line=infile.readline().strip()
	def _write_strs(self,outfile):								#Writes STRS and associated macros.
		ws = _title_string('STRESS MODULE',72)
		outfile.write(ws)
		outfile.write('strs\n')
		outfile.write(str(self.strs.param['ISTRS'])+'\t')
		outfile.write(str(self.strs.param['IHMS'])+'\n')
		if self.strs.bodyforce: outfile.write('bodyforce\n')
		if self.strs.initcalc: outfile.write('initcalc\n')
		if self.strs.fem: outfile.write('fem\n')
		if self.strs.excess_she['PAR1']:
			outfile.write('excess_she\n')
			outfile.write(str(self.strs.excess_she['PAR1'])+'\t')
			if self.strs.excess_she['PAR2']: outfile.write(str(self.strs.excess_she['PAR2'])+'\t')
			if self.strs.excess_she['PAR3']: outfile.write(str(self.strs.excess_she['PAR3'])+'\t')
			outfile.write('\n')
		if self.permmodellist: self._write_model(outfile,'permmodel')
		if self.stressbounlist: self._write_macro(outfile,'stressboun')
		if self.elasticlist: self._write_macro(outfile,'elastic')
		if self.biotlist: self._write_macro(outfile,'biot')
		outfile.write('tolerance\n')
		outfile.write(str(self.strs.tolerance)+'\n')
		outfile.write('stressend\n')
	def _read_ngas(self,infile):							#NGAS: Reads NGAS and associated macros.
		line = infile.readline().strip().split()
		self.ngas.dof = int(float(line[0]))
		# read initial pressures
		line = infile.readline().strip()
		while line:
			nums = line.split()
			self.ngas.add_init_pres(self._macro_zone(nums[:3]),float(nums[-1]))
			line = infile.readline().strip()
		# read ncg pressures
		line = infile.readline().strip()
		while line:
			nums = line.split()
			self.ngas.add_ncg_pres(self._macro_zone(nums[:3]),float(nums[-1]))
			line = infile.readline().strip()
		# read sources 
		line = infile.readline().strip()
		while line:
			nums = line.split()
			self.ngas.add_source(self._macro_zone(nums[:3]),float(nums[-1]))
			line = infile.readline().strip()
	def _write_ngas(self,outfile):								#Writes NGAS and associated macros.
		ws = _title_string('NONCONDENSIBLE GAS MODULE',72)
		outfile.write(ws)
		if self.sticky_zones:
			zns = []
			zns += self.ngas.init_pres.keys()
			zns += self.ngas.ncg_pres.keys()
			zns += self.ngas.source.keys()
			zns2 = []
			for zn in zns:
				if isinstance(zn,tuple): zns2.append(zn)
				elif isinstance(zn,(int,str)): 
					if zn in self.zone.keys():
						zns2.append(self.zone[zn])
					else: 'WARNING: no zone '+str(zn)+ ' found'
			self._write_zonn_one(outfile,list(set(zns2)))
		outfile.write('ngas\n')
		outfile.write(str(int(self.ngas.dof))+'\n')
		if 0 in self.ngas.init_pres.keys():
			outfile.write('1\t0\t0\t'+str(self.ngas.init_pres[0])+'\n')
		for k in self.ngas.init_pres.keys():
			if k == 0: continue
			if isinstance(k,tuple):
				outfile.write(str(k[0])+'\t'+str(k[1])+'\t'+str(k[1])+'\t'+str(self.ngas.init_pres[k])+'\n')
			elif isinstance(k, int):
				outfile.write('-'+str(k)+'\t0\t0\t'+str(self.ngas.init_pres[k])+'\n')
		outfile.write('\n')
		
		if 0 in self.ngas.ncg_pres.keys():
			outfile.write('1\t0\t0\t'+str(self.ngas.ncg_pres[0])+'\n')
		for k in self.ngas.ncg_pres.keys():
			if k == 0: continue
			if isinstance(k,tuple):
				outfile.write(str(k[0])+'\t'+str(k[1])+'\t'+str(k[1])+'\t'+str(self.ngas.ncg_pres[k])+'\n')
			elif isinstance(k, int):
				outfile.write('-'+str(k)+'\t0\t0\t'+str(self.ngas.ncg_pres[k])+'\n')
		outfile.write('\n')
		
		if 0 in self.ngas.source.keys():
			outfile.write('1\t0\t0\t'+str(self.ngas.source[0])+'\n')
		for k in self.ngas.source.keys():
			if k == 0: continue
			if isinstance(k,tuple):
				outfile.write(str(k[0])+'\t'+str(k[1])+'\t'+str(k[1])+'\t'+str(self.ngas.source[k])+'\n')
			elif isinstance(k, int):
				outfile.write('-'+str(k)+'\t0\t0\t'+str(self.ngas.source[k])+'\n')
		outfile.write('\n')
	def _read_text(self,infile):							#TEXT: Reads TEXT macro.
		more=True
		line=infile.readline().strip()
		new_text = []
		while more:
			new_text.append(line)
			line=infile.readline().strip()
			if not line: more=False
		self.text.append(new_text)
	def _write_text(self,outfile):								#Writes TEXT macro.
		for text in self.text:
			outfile.write('text\n')
			for line in text: outfile.write(line)			
		outfile.write('\n\n')	
	def _read_trac(self,infile):							#TRAC: Reads TRAC and associated macros.
		self.trac._on = True
		# group 1
		nums=infile.readline().strip().split()
		self.trac.param['init_solute_conc_ANO'] = float(nums[0])
		self.trac.param['implicit_factor_AWC'] = float(nums[1])
		self.trac.param['tolerance_EPC'] = float(nums[2])
		self.trac.param['upstream_weight_UPWGTA'] = float(nums[3])
		# group 2
		nums=infile.readline().strip().split()
		self.trac.param['solute_start_DAYCS'] = float(nums[0])
		self.trac.param['solute_end_DAYCF'] = float(nums[1])
		self.trac.param['flow_end_DAYHF'] = float(nums[2])
		self.trac.param['flow_start_DAYHS'] = float(nums[3])
		# group 3
		line=infile.readline().strip()
		nums = line.split()
		self.trac.param['max_iterations_IACCMX'] = float(nums[0])
		self.trac.param['timestep_multiplier_DAYCM'] = float(nums[1])
		self.trac.param['initial_timestep_DAYCMM'] = float(nums[2])
		self.trac.param['max_timestep_DAYCMX'] = float(nums[3])
		self.trac.param['print_interval_NPRTTRC'] = float(nums[4])
		# groups 4 and 5 (if applicable)
		line=infile.readline().strip()
		if line.startswith('tpor'):
			nums=infile.readline().strip().split()
			self.trac.transport_porosity = float(nums[-1])
			line=infile.readline().strip()
			line=infile.readline().strip()
		# group 6
		num_species = int(line.split()[0])
		# group 7
		line=infile.readline().strip()
		if line.startswith('ldsp'): 
			self.trac.ldsp = True
			line=infile.readline().strip()
		# groups 8, 9 and 10
		sorptionOnly = False
		keepReading = True
		if line.startswith('dspl') or line.startswith('dspv'):
			sorptionOnly = True
			# read models
			while keepReading:
				line=infile.readline().strip()
				if not line: break
				nums = line.split()
				if not self.trac.ldsp:
					self.trac.add_common_model(diffusion_model=int(float(nums[0])),
							diffusion = float(nums[1]), 
							dispersion = [float(nums[2]),float(nums[3]),float(nums[4])])
				else:
					self.trac.add_common_model(diffusion_model=int(float(nums[0])),
							diffusion = float(nums[1]), 
							dispersion = [float(nums[2]),float(nums[3]),None])
			# read model-zone assignment
			zns = []; inds = []
			while keepReading:
				line=infile.readline().strip()
				if not line: break
				nums = line.split()
				zns.append(self._macro_zone(nums))
				inds.append(int(float(nums[-1])))
			for zn,ind in zip(zns,inds):
				self.trac.common_modellist[ind-1].zone = zn
			line=infile.readline().strip()
			self.trac.common_modellist.sort(key=lambda x: x.zone.index)
		# group 11 - 16
		for i in range(num_species):
			nums=line.split()
			phase = int(float(nums[0]))
			
			if phase: 
				models1,models2 = self._read_model_trac(infile,self.trac.ldsp)
				'''
				UNDER CONSTRUCTION !!!
				'''
				#nums=infile.readline().strip().split()
				#adsorption_model=None
				#adsorption=None
				#diffusion_model=None
				#diffusion=None
				#dispersion=None
				#adsorption_model = int(float(nums[0]))
				#adsorption = [float(nums[1]),float(nums[2]),float(nums[3])]
				#if not sorptionOnly:
				#	if len(nums) == 9: diffusion_model = int(float(nums[4])); nums = nums[5:]
				#	elif len(nums) == 8: diffusion_model = 0; nums = nums[4:]
				#	diffusion = float(nums[0])
				#	if self.trac.ldsp:
				#		dispersion = [float(nums[1]),float(nums[2]),None]
				#	else:
				#		dispersion = [float(nums[1]),float(nums[2]),float(nums[3])]
				#
				#line=infile.readline().strip()			
				#line=infile.readline().strip()			
				#line=infile.readline().strip()	
			#line=infile.readline().strip()	
			self.trac.add_species(phase,adsorption_model,adsorption,diffusion_model,diffusion,dispersion)
			# read in initial concentrations
			while keepReading:
				if not line: break
				nums = line.split()
				self.trac.specieslist[-1].add_tracer_concentration(zone=self._macro_zone(nums),
					initial_concentration=float(nums[-1]))	
				line=infile.readline().strip()		
			# read in injection concentrations
			while keepReading:
				line=infile.readline().strip()
				if not line: break
				print nums
				self.trac.specieslist[-1].add_tracer_generator(zone=self._macro_zone(nums),
					injection_concentration=float(nums[3]),time_start=float(nums[4]),time_end=float(nums[5]))
			line=infile.readline().strip()
	def _write_trac(self,outfile):								#Writes TRAC and associated macros.
		ws = _title_string('TRACKING MODULE',72)
		outfile.write(ws)
		if self.sticky_zones:
			zns = []
			for sp in self.trac.specieslist:
				zns += [m.zone for m in sp._tracer_concentrationlist if m.zone.index]
				zns += [m.zone for m in sp._tracer_generatorlist if m.zone.index]
			self._write_zonn_one(outfile,list(set(zns)))
		outfile.write('trac\n')
		# group 1
		outfile.write(str(self.trac.param['init_solute_conc_ANO'])+'\t')
		outfile.write(str(self.trac.param['implicit_factor_AWC'])+'\t')
		outfile.write(str(self.trac.param['tolerance_EPC'])+'\t')
		outfile.write(str(self.trac.param['upstream_weight_UPWGTA'])+'\n')
		# group 2
		outfile.write(str(self.trac.param['solute_start_DAYCS'])+'\t')
		outfile.write(str(self.trac.param['solute_end_DAYCF'])+'\t')
		outfile.write(str(self.trac.param['flow_end_DAYHF'])+'\t')
		outfile.write(str(self.trac.param['flow_start_DAYHS'])+'\n')
		# group 3
		outfile.write(str(int(self.trac.param['max_iterations_IACCMX']))+'\t')
		outfile.write(str(self.trac.param['timestep_multiplier_DAYCM'])+'\t')
		outfile.write(str(self.trac.param['initial_timestep_DAYCMM'])+'\t')
		outfile.write(str(self.trac.param['max_timestep_DAYCMX'])+'\t')
		outfile.write(str(int(self.trac.param['print_interval_NPRTTRC']))+'\n')
		# groups 4 and 5 (if applicable)
		if self.trac.transport_porosity != -1:
			outfile.write('tpor\n')
			outfile.write('1 0 0 '+str(self.trac.transport_porosity)+'\n')
			outfile.write('\n')
		# group 6
		outfile.write(str(self.trac.number_species)+'\n')
		# group 7
		if self.trac.ldsp: 
			outfile.write('ldsp\n')
		# groups 8, 9 and 10
		sorptionOnly = False
		if self.trac.common_modellist: sorptionOnly = True
		keepReading = True
		if sorptionOnly:
			outfile.write('dspl\n')
			for cm in self.trac.common_modellist:
				outfile.write(str(int(cm.diffusion_model))+'\t')
				outfile.write(str(cm.diffusion)+'\t')
				outfile.write(str(cm.dispersion[0])+'\t')
				outfile.write(str(cm.dispersion[1])+'\t')
				if not self.trac.ldsp: outfile.write(str(cm.dispersion[2])+'\t')
				outfile.write('\n')				
			outfile.write('\n')
			for i,cm in enumerate(self.trac.common_modellist):
				zn = cm.zone
				if not zn.index: outfile.write(str(1)+'\t'+'0\t0\t')
				else: outfile.write(str(-zn.index)+'\t'+'0\t0\t') 
				outfile.write(str(i+1)+'\n')
			outfile.write('\n')
		# group 11 - 16
		for i,sp in enumerate(self.trac.specieslist):
			# group 11
			outfile.write(str(int(sp.phase))+'\n')
			
			if sp.phase:
				outfile.write(str(int(sp.adsorption_model))+'\t')
				outfile.write(str(int(sp.adsorption[0]))+'\t')
				outfile.write(str(int(sp.adsorption[1]))+'\t')
				outfile.write(str(int(sp.adsorption[2]))+'\t')
				if not sorptionOnly:
					outfile.write(str(int(sp.diffusion_model))+'\t')
					outfile.write(str(sp.diffusion)+'\t')
					outfile.write(str(sp.dispersion[0])+'\t')
					outfile.write(str(sp.dispersion[1])+'\t')
					if not self.trac.ldsp: outfile.write(str(sp.dispersion[2])+'\t')
				outfile.write('\n')
				outfile.write('\n')
				outfile.write('1 0 0 1 \n')
				outfile.write('\n')
			for ic in sp._tracer_concentrationlist:
				zn = ic.zone
				if not zn.index: outfile.write(str(1)+'\t'+'0\t0\t')
				else: outfile.write(str(-zn.index)+'\t'+'0\t0\t') 
				outfile.write(str(ic.initial_concentration)+'\n')
			outfile.write('\n')
			for ic in sp._tracer_generatorlist:
				zn = ic.zone
				if not zn.index: outfile.write(str(1)+'\t'+'0\t0\t')
				else: outfile.write(str(-zn.index)+'\t'+'0\t0\t') 
				outfile.write(str(ic.injection_concentration)+'\n')
				outfile.write(str(ic.time_start)+'\n')
				outfile.write(str(ic.time_end)+'\n')
			outfile.write('\n')
		# concentration dependent density - only the first will be written
		for i,sp in enumerate(self.trac.specieslist):
			if sp.density_modifier: 
				poutfile.write('cden\n')
				outfile.write(str(i+1)+'\n')
				outfile.write(str(sp.density_modifier)+'\n')
				outfile.write('\n')
				break
	def _read_time(self,infile):							#TIME: Reads TIME macro.
		line=infile.readline()
		nums = line.split()
		for i in range(7-len(nums)): nums.append(None)
		for num, param in zip(nums,['initial_timestep_DAY','max_time_TIMS','max_timestep_NSTEP','print_interval_IPRTOUT','initial_year_YEAR','initial_month_MONTH','initial_day_INITTIME']):
			if not num: self.time[param] = num
			else: self.time[param] = float(num)
		line=infile.readline().strip()
		while line.strip():
			nums = line.split()
			time = np.array([float(num) for num in nums])
			self.times.append(time)
			line=infile.readline().strip()
		self.tf = self.time['max_time_TIMS']
		self.dtn = self.time['max_timestep_NSTEP']
		self.dti = self.time['initial_timestep_DAY']
	def _write_time(self,outfile):								#Writes TIME macro.
		ws = _title_string('TIME STEPPING PARAMETERS',72)
		outfile.write(ws)
		outfile.write('time\n')
		if not self.time['initial_timestep_DAY']==None: outfile.write(str(self.time['initial_timestep_DAY'])+'\t')
		if not self.time['max_time_TIMS']==None: outfile.write(str(self.time['max_time_TIMS'])+'\t')
		if not self.time['max_timestep_NSTEP']==None: outfile.write(str(int(self.time['max_timestep_NSTEP']))+'\t')
		if not self.time['print_interval_IPRTOUT']==None: outfile.write(str(int(self.time['print_interval_IPRTOUT']))+'\t')
		if not self.time['initial_year_YEAR']==None: outfile.write(str(self.time['initial_year_YEAR'])+'\t')
		if not self.time['initial_month_MONTH']==None: outfile.write(str(self.time['initial_month_MONTH'])+'\t')
		if not self.time['initial_day_INITTIME']==None: outfile.write(str(self.time['initial_day_INITTIME'])+'\t')
		outfile.write('\n')
		if self.times:
			for time in self.times:
				for t_cpt in time: outfile.write(str(t_cpt)+'\t')					
				outfile.write('\n')
		outfile.write('\n')
	def print_time(self):										#Prints out variables contained in TIME.
		'''Display contents of TIME macro.
		'''
		for k in self.time.keys():	print k +': ' + str(self.time[k])
	def change_timestepping(self,at_time,new_dti=None,new_dtmax=None,new_dtx=None,new_implicitness=None,new_print_out=None):
		''' Change timestepping during a simulation. Note, if time stepping arguments are omitted, FEHM will force output
		to be written at the change time. The default for all optional arguments is no change.
			
		:param at_time: Simulation time to change time stepping behaviour.
		:type at_time: fl64
		:param new_dti: Initial time step at change time.
		:type new_dti: fl64
		:param new_dtmax: New maximum time step after change time.
		:type new_dtmax: fl64
		:param new_dtx: New time step multiplier at change time.
		:type new_dtx: fl64
		:param new_implicitness: New implicitness factor at change time.
		:type new_implicitness: fl64
		:param new_print_out: New time step interval at which to print information. 
		:type new_print_out: int
		'''
		
		# load old parameters
		self._output_times = []
		if self.times:
			DIT1,DIT2,DIT3,ITC,DIT4 = self.times[-1]
			if DIT2>0: DIT2a = DIT2; DIT2b = -self.dtx
			else: DIT2b = DIT2; DIT2a = None
		else:
			DIT2b = -self.dtx
			DIT3 = self.ctrl['implicitness_factor_AAW']
			ITC = self.time['print_interval_IPRTOUT']
			DIT4 = self.dtmax
		
		# assign new parameters
		DIT1 = at_time
		if new_dti and new_dtx:
			print 'WARNING: you cannot specify BOTH a new time step size and time step multiplier. Ignoring the new multiplier...'
			new_dtx = None
		if new_dti: DIT2 = new_dti
		elif new_dtx: DIT2 = -new_dtx
		else: DIT2 = DIT2b
		if new_implicitness: DIT3 = new_implicitness
		if new_print_out: ITC = new_print_out
		if new_dtmax: DIT4 = new_dtmax
		
		self.times.append([DIT1,DIT2,DIT3,ITC,DIT4])		
	def _read_vapl(self,infile):							#VAPL: Reads VAPL macro.
		self.vapl=True
	def _write_vapl(self,outfile):								#Writes VAPL macro.
		if self.vapl:
			outfile.write('vapl\n')
	def new_zone(self,index,name=None,rect=None,nodelist=None,file=None,permeability=None,conductivity=None,density=None,
		specific_heat=None,porosity=None,youngs_modulus=None,poissons_ratio=None,thermal_expansion=None,pressure_coupling=None,
		Pi=None,Ti=None,Si=None,overwrite=False):
		''' Create and assign a new zone. Material properties are optionally specified, new macros will be created if required.
		
		:param index: Zone index.
		:type index: int
		:param name: Zone name.
		:type name: str
		:param rect: Two item list. Each item is itself a three item (or two for 2D) list containing [x,y,z] coordinates of zone bounding box.
		:type rect: lst
		:param nodelist: List of node objects or indices of zone. Only one of rect or nodelist should be specified (rect will be taken if both given).
		:type nodelist: lst
		:param file: Name of auxiliary file for zone
		:type file: str
		:param permeability: Permeability of zone. One float for isotropic, three item list [x,y,z] for anisotropic.
		:type permeability: fl64, list
		:param conductivity: Conductivity of zone. One float for isotropic, three item list [x,y,z] for anisotropic.
		:type conductivity: fl64, list
		:param density: Density of zone. If not specified, defaults will be used for specific heat and porosity.
		:type density: fl64
		:param specific_heat: Specific heat of zone. If not specified, defaults will be used for density and porosity.
		:type specific_heat: fl64
		:param porosity: Porosity of zone. If not specified, defaults will be used for density and specific heat.
		:type porosity: fl64
		:param youngs_modulus: Young's modulus of zone. If not specified, default will be used for Poisson's ratio.
		:type youngs_modulus: fl64
		:param poissons_ratio: Poisson's ratio of zone. If not specified, default will be used for Young's modulus.
		:type poissons_ratio: fl64
		:param thermal_expansion: Coefficient of thermal expansion for zone. If not specified, default will be used for pressure coupling term.
		:type thermal_expansion: fl64
		:param pressure_coupling: Pressure coupling term for zone. If not specified, default will be used for coefficient of thermal expansion.
		:type pressure_coupling: fl64
		:param Pi: Initial pressure in the zone. If not specified, default will be used for initial temperature and saturation calculated.
		:type Pi: fl64
		:param Ti: Initial temperature in the zone. If not specified, default will be used for initial pressure and saturation calculated.
		:type Ti: fl64
		:param Si: Initial saturation in the zone. If not specified, default will be used for initial pressure and the saturation temperature calculated.
		:type Si: fl64
		:param overwrite: If zone already exists, delete it and create the new one.
		:type overwrite: bool
		'''
		
		# if neither rect nor nodelist specified, not enough information to create the zone
		if not rect and not nodelist:
			print 'ERROR: either rect or nodelist must be specified'
			return
		# if both rect and nodelist are specified, proceed with rect, print warning
		if rect and nodelist:
			print 'WARNING: only one of rect or nodelist should be specified, proceeding with rect values'
		if nodelist:
			if isinstance(nodelist,fnode) or isinstance(nodelist,int): nodelist = [nodelist]
			nds = []
			for nd in nodelist:
				if isinstance(nd,int): nds.append(self.grid.node[nd])
				else: nds.append(nd)
			nodelist = nds
		# determine if zone already exists, delete or exit
		if index in self.zone.keys():
			if overwrite:
				self.delete(self.zone[index])
			else:
				print 'ERROR: specified zone already exists, overwrite flag set to false'
				return
		
		# assemble zone
		zn = fzone(index=index,name=name,file=file)
		if rect:
			zn.rect(rect[0],rect[1])
		elif nodelist:
			zn.type = 'nnum'
			nds = []
			for nd in nodelist:
				if isinstance(nd,int):
					if nd in self.grid.node.keys(): nds.append(self.grid.node[nd])
				elif isinstance(nd,fnode): nds.append(nd)
			zn.nodelist = nds
		self.add(zn)
		# add permeability property macros
		if permeability:
			if not (isinstance(permeability,(int,float)) or (isinstance(permeability,list) and len(permeability) == 3)):
				print 'ERROR: permeability must be a single float (isotropic) or three item list ([x,y,z] anisotropic'
				return
			# unpack values
			if isinstance(permeability,(int,float)):
				kx,ky,kz = [permeability,permeability,permeability]
			else:
				kx,ky,kz = permeability
			# assign
			if index in self.perm.keys():
				self.perm[index].param['kx'] = kx
				self.perm[index].param['ky'] = ky
				self.perm[index].param['kz'] = kz
			else:
				macro = fmacro('perm',zone=index,param=(('kx',kx),('ky',ky),('kz',kz)))
				self.add(macro)
			self.zone[index]._permeability = permeability
		# add conductivity property macros
		if conductivity:
			if not (isinstance(conductivity,(int,float)) or (isinstance(conductivity,list) and len(conductivity) == 3)):
				print 'ERROR: conductivity must be a single float (isotropic) or three item list ([x,y,z] anisotropic'
				return
			# unpack values
			if isinstance(conductivity,(int,float)):
				kx,ky,kz = [conductivity,conductivity,conductivity]
			else:
				kx,ky,kz = conductivity
			# assign
			if index in self.cond.keys():
				self.cond[index].param['cond_x'] = kx
				self.cond[index].param['cond_y'] = ky
				self.cond[index].param['cond_z'] = kz
			else:
				macro = fmacro('cond',zone=index,param=(('cond_x',kx),('cond_y',ky),('cond_z',kz)))
				self.add(macro)
			self.zone[index]._conductivity = conductivity
		# add rock property macros
		if density or specific_heat or porosity:
			if not density:
				print 'WARNING: No density specified, assigning default '+str(dflt.density)
				density = dflt.density
			
			if not specific_heat:
				print 'WARNING: No specific heat specified, assigning default '+str(dflt.specific_heat)
				specific_heat = dflt.specific_heat
			
			if not porosity:
				print 'WARNING: No porosity specified, assigning default '+str(dflt.porosity)
				porosity = dflt.porosity
						
			# assign
			if index in self.rock.keys():
				self.rock[index].param['density'] = density
				self.rock[index].param['specific_heat'] = specific_heat
				self.rock[index].param['porosity'] = porosity
			else:
				macro = fmacro('rock',zone=index,param=(('density',density),('specific_heat',specific_heat),('porosity',porosity)))
				self.add(macro)
			self.zone[index]._density = density
			self.zone[index]._specific_heat = specific_heat
			self.zone[index]._porosity = porosity
		# add elastic property macros
		if youngs_modulus or poissons_ratio:
			if not youngs_modulus:
				print 'WARNING: No Youngs modulus specified, assigning default '+str(dflt.youngs_modulus)
				youngs_modulus = dflt.youngs_modulus
			
			if not poissons_ratio:
				print 'WARNING: No Poissons ratio specified, assigning default '+str(dflt.poissons_ratio)
				poissons_ratio = dflt.poissons_ratio
			
			# assign
			if index in self.elastic.keys():
				self.elastic[index].param['youngs_modulus'] = youngs_modulus
				self.elastic[index].param['poissons_ratio'] = poissons_ratio
			else:
				macro = fmacro('elastic',zone=index,param=(('youngs_modulus',youngs_modulus),('poissons_ratio',poissons_ratio)))
				self.add(macro)
			self.zone[index]._youngs_modulus = youngs_modulus
			self.zone[index]._poissons_ratio = poissons_ratio
		# add stress coupling property macros
		if thermal_expansion or pressure_coupling:
			if not thermal_expansion:
				print 'WARNING: No coefficient of thermal expansion specified, assigning default '+str(dflt.thermal_expansion)
				thermal_expansion = dflt.thermal_expansion
			
			if not pressure_coupling:
				print 'WARNING: No pressure coupling term specified, assigning default '+str(dflt.pressure_coupling)
				pressure_coupling = dflt.pressure_coupling
			
			# assign
			if index in self.biot.keys():
				self.biot[index].param['thermal_expansion'] = thermal_expansion
				self.biot[index].param['pressure_coupling'] = pressure_coupling
			else:
				macro = fmacro('biot',zone=index,param=(('thermal_expansion',thermal_expansion),('pressure_coupling',pressure_coupling)))
				self.add(macro)
			self.zone[index]._thermal_expansion = thermal_expansion
			self.zone[index]._pressure_coupling = pressure_coupling
		# add initial conditions macros
		if Pi or Ti or Si:
			if not Si and Pi and Ti:
				if Ti < tsat(Pi)[0]: Si = 1.; si = 1
				else: Si = 0.; si = 3
				ti = Ti
				
			elif not Si and Pi and not Ti:
				print 'WARNING: No initial temperature specified, assigning default '+str(dflt.Ti)
				Ti = dflt.Ti
				if Ti < tsat(Pi)[0]: Si = 1.; si = 1
				else: Si = 0.; si = 3
				ti = Ti
			
			elif not Si and Ti and not Pi:
				Pi = dflt.Pi
				print 'WARNING: No initial pressure specified, assigning default '+str(dflt.Pi)
				if Ti < tsat(Pi)[0]: Si = 1.; si = 1
				else: Si = 0.; si = 3
				ti = Ti
				
			elif Si and Ti and not Pi:
				Pi = sat(Ti)[0]
				print 'NOTE: For supplied saturation '+str(Si)+' and temperature '+str(Ti)+', saturation pressure of '+str(Pi)+' will be used.'
				
				ti = Si
				si = 2
			
			elif Si and Pi:
				if Ti:
					print 'WARNING: Ignoring Ti, using Pi to calculate saturation temperature.'
				Ti = tsat(Pi)[0]
				
				ti = Si
				si = 2
			
			elif Si and not Ti and not Pi:
				Pi = dflt.Pi
				Ti = tsat(Pi)[0]
				
				print 'WARNING: No initial pressure specified, assigning default '+str(dflt.Pi)
				print 'NOTE: For supplied saturation '+str(Si)+' and default pressure '+str(Pi)+', saturation temperature of '+str(Ti)+' will be used.'
				
				ti = Si
				si = 2
			
			# assign
			if index in self.pres.keys():
				self.pres[index].param['pressure'] = Pi
				self.pres[index].param['temperature'] = ti
				self.pres[index].param['saturation'] = si
			else:
				macro = fmacro('pres',zone=index,param=(('pressure',Pi),('temperature',ti),('saturation',si)))
				self.add(macro)
				
			self.zone[index]._Pi = Pi
			self.zone[index]._Ti = Ti
			self.zone[index]._Si = Si
	def run(self,input='',grid = '',incon='',exe=dflt.fehm_path,files=dflt.files,verbose = None, until=None,autorestart=0,use_paths=False):
		'''Run an fehm simulation. This command first writes out the input file, *fehmn.files* and this incon file
		if changes have been made. A command line call is then made to the FEHM executable at the specified path (defaults
		to *fehm.exe* in the working directory if not specified).
		
		:param input: Name of input file. This will be written out.
		:type input: str
		:param grid: Name of grid file. This will be written out.
		:type grid: str
		:param incon: Name of restart file.
		:type incon: str
		:param exe: Path to FEHM executable.
		:type exe: str
		:param files: List of additional files to output. Options include 'check', 'hist' and 'outp'.
		:type files: lst[str]
		:param until: Name of a function defined inside the script. The function returns a boolean indicating the simulation should be halted. See manual for usage.
		:type until: func
		:param autorestart: Number of times FEHM should restart itself in attempting to find a solution.
		:type autorestart: int
		:param use_paths: Flag to indicate that PyFEHM should favour full paths in fehmn.files rather than duplication of source files.
		:type use_paths: bool
		'''
		
		if verbose != None: self.files._verbose = verbose
		
		# set up and check path to executable
		exe_path = fpath()
		exe_path.filename = exe
		
		if not os.path.isfile(exe_path.full_path): 	# if can't find the executable, halt
			print 'ERROR: No executable at location '+exe
			return
		
		tempRstoFlag = False
		if until is not None and self.files.rsto == '':	tempRstoFlag = True
						
		# if using 'until' to break a simulation, we require a restart file to be written each timestep
		# restart files are written at the same frequency as contour output, hence contour output will
		# need to be written every timestep - manage this data by deleting it
		contUnchanged = True 			# flag to indicate whether we have modified cont
		if until:
			if self.cont.timestep_interval == 1 and self.cont.variables: contUnchanged = True
			else:
				from copy import deepcopy
				oldCont = deepcopy(self.cont)
				if not self.cont.variables: self.cont.variables.append('temperature')
				self.cont.timestep_interval = 1
				contUnchanged = False
				
		# option to write input, grid, incon files to new names
		if input: self._path.filename = input
		if grid: self.grid._path.filename = grid
		if incon: self.incon._path.filename = incon
		
		# ASSEMBLE FILES IN CORRECT DIRECTORIES
		if self.work_dir: wd = self.work_dir + slash
		else: wd = os.getcwd() + slash
		self.write(wd+self._path.filename) 				# ALWAYS write input file
		self.files.input = self._path.filename
		# 1. Copy everything to working directory 
		if not use_paths:
			self.grid.write(wd+self.grid._path.filename)	# SOMETIMES write grid file
			self.files.grid = self.grid._path.filename
			if self.files._use_incon:
				self.incon.write(wd+self.incon._path.filename)	# SOMETIMES write incon file
				self.files.incon = self.incon._path.filename
			if self.files._use_stor:						# SOMETIMES copy stor file
				temp_path = fpath()
				temp_path.filename = self.files.stor
				if os.path.isfile(temp_path.full_path):
					shutil.copyfile(temp_path.full_path,wd+filename)
				else:
					print 'ERROR: cant find stor file at '+temp_path.full_path
					return
		else:	
			self.files.grid = self.grid._path.full_path
			if self.files._use_incon:
				self.files.incon = self.incon._path.full_path
						
		for file in files: 												# extra files to be written
			if file == 'chk': self.files._use_check = True
			if file == 'check': self.files._use_check = True
			if file == 'hist': self.files._use_hist = True
			if file == 'outp': self.files._use_outp = True
			
		if self.ctrl['stor_file_LDA']: self.files._use_stor = True 		# stor file requested?
			
		self.files.write()				# ALWAYS write fehmn.files
		self.files.exe = exe
		# RUN SIMULATION
		cwd = os.getcwd()
				
		# summarize simulation
		self.grid._summary()
		if self.files.incon: self.incon._summary()
		self._summary()		
		#self.write()
		
		#self.files.write()

		if self.work_dir: os.chdir(self.work_dir)
		
		# remove restart file if left over from old simulation
		if until and self.incon.time == None and os.path.isfile(self.files.rsto):
			os.remove(self.files.rsto)
			
		# run the simulation
		breakAutorestart = False
		for attempt in range(autorestart+1): 	# restart execution
			if breakAutorestart: break
			untilFlag = False
			p = Popen(exe)
			if until is None:
				p.communicate()
			else:
				self._running = True
				interval = 0
				delFiles = []
				while self._running:					# loop for checking if stop condition is met
					sleep(dflt.sleep_time) 					# wait 
					is_new = self.incon.read(self.files.rsto, if_new = True) 	# read new input file
					if is_new: 
						untilFlag = until(self) 				# check stop condition
						if not contUnchanged: #delete cont file that was created
							
							if delFiles: 
								for delFile in delFiles: os.remove(delFile)
							delFiles = []
								
							interval += 1
							if interval%oldCont.timestep_interval == 0: continue
							
							if self.cont.type == 'surf': suffix = 'csv'
							elif self.cont.type == 'tec': suffix = 'dat'
							elif self.cont.type == 'avsx': suffix = 'avsx'
							
							# use glob to find most recently created file							
							from glob import glob
							outtypes = ['_vec','_sca','_con']
							for outtype in outtypes:
								files = filter(os.path.isfile, glob(self.files.root+'*'+outtype+'*.'+suffix))
								if not files: continue
								files.sort(key=lambda x: os.path.getmtime(x))
								files = files[-2:]
							
								# delete file if 
								ts = [fl.split(outtype)[0] for fl in files]
								ts = [fl.split('_days')[0] for fl in ts]
								ts = [fl.split('.')[-2:] for fl in ts]
								ts = [float(tsi[0]+'.'+tsi[1]) for tsi in ts]
								
								if (1-(abs(ts[0]-ts[1])/oldCont.time_interval)) <0.001: continue
								delFiles.append(files[-1])
							
					p.poll() 								# check if run finished on its own
					if p.returncode == 0:					# IF run finshed on its own
						self._running = False					# break the loop
					if untilFlag and self._running: 		# IF stop condition met
						p.terminate()							# kill the process
						self._running = False					# break the loop
						breakAutorestart = True
			
			self.incon.read(self.files.rsto) 		# read fin file for autorestart
			if abs((self.incon.time - self.tf)/self.tf)<0.001: breakAutorestart = True
						
		if not contUnchanged: 
			if self.cont.type == 'surf': suffix = 'csv'
			elif self.cont.type == 'tec': suffix = 'dat'
			elif self.cont.type == 'avsx': suffix = 'avsx'
			self._cont = oldCont
			if len(self.cont.variables) == 0:
				outtypes = ['_vec','_sca','_con']
				for outtype in outtypes:
					files = filter(os.path.isfile, glob(self.files.root+'*'+outtype+'*.'+suffix))
					if files:
						for file in files: os.remove(file)
				
		if self.work_dir: os.chdir(cwd)
		
		if tempRstoFlag: 
			self.files.incon = ''
			self.files.write()
	def _summary(self):		
		L = 62
		print ''
		print ' ****---------------------------------------------------------****'
		line = ' **** FEHM input file \''+self.filename+'\' summary.'
		for i in range(L-len(line)): line += ' '
		print line+'****'
		print ' ****---------------------------------------------------------****'
		
		lines = []
		lines.append(' **** Zones:')
		lines.append(' **** Material properties:')
		lines.append(' **** Generators:')
		
		for line in lines:
			if line.startswith(' **'):
				for i in range(L-len(line)): line += ' '
				print line+'****'
			else:
				prntStr = ' **** -'
				keepGoing = True
				line = line.split()
				while keepGoing:
					if not line: 
						for i in range(L-len(prntStr)): prntStr += ' '
						print prntStr+'****'
						prntStr = ' **** '
						break
					if len(prntStr)<(L-len(line[0])): 
						prntStr += ' '+line[0]
						line = line[1:]
					else:
						for i in range(L-len(prntStr)): prntStr += ' '
						print prntStr+'****'
						prntStr = ' ****   '
		print ' ****---------------------------------------------------------****'
		print ''
	def _write_prep(self):									#Determine if data object fit for writing
		# WARNING: if cont output specifies pressure, but not state, then no pressure data will be written
		hasPres = False
		hasState = False
		warnings = []
		for var in list(flatten(self.cont.variables)):
			if var.startswith('p') and not var.startswith('po') and not var.startswith('pe'): hasPres = True
			if var.startswith('l') or var.startswith('va'): hasState=True
		if hasPres and not hasState: self.cont.variables.append(['liquid','vapor'])
		# WARNING: stress perm module specified without calling excess_she
		if self.permmodellist:
			for pm in self.permmodellist:
				if pm.index in [22,24,25] and self.strs.excess_she['PAR1']==None:
					warnings.append('Perm model specified without accompanying excess_she macro - assigning defaults.')
					self.strs.excess_she['PAR1']=0.9
					self.strs.excess_she['PAR2']=10.
					self.strs.excess_she['PAR3']=1.
		for boun in self.bounlist: boun._check()
		for zone in self.zonelist: zone._check()
		for key in self._allMacro.keys():
			for macro in self._allMacro[key]: macro._check()
		# WARNING: conductivity not specified, FEHM simulation wont run - add default
		if not self.cond.has_key(0): 
			warnings.append('No global conductivity set. Setting default '+str(dflt.conductivity))
			self.add(fmacro('cond',param=(('cond_x',dflt.conductivity),('cond_y',dflt.conductivity),('cond_z',dflt.conductivity))))
		# WARNING: rock properties not specified, FEHM will run weirdly - add default
		if not self.rock.has_key(0): 
			warnings.append('No global rock properties set. Setting default density = '+str(dflt.density)+', specific heat = '+str(dflt.specific_heat)+', porosity='+str(dflt.porosity))
			self.add(fmacro('rock',param=(('density',dflt.density),('specific_heat',dflt.specific_heat),('porosity',dflt.porosity))))
		# WARNING: specifying zero pressure in co2pres has caused segfaults in the past
		if self.co2preslist:
			for m in self.co2preslist:
				if m.param['pressure'] == 0:
					print warnings.append('Zero pressure  in CO2PRES can cause instability.')
					break
		# WARNING: if stress gradients have been specified and bodyforce applied
		if self.incon._stressgradCalled and self.strs.bodyforce:
			warnings.append('When specifying stress gradients, bodyforce should be turned off.')
		if (len(self.incon._strs_xx) != 0) and self.strs.bodyforce:
			warnings.append('Bodyforce should be turned off when doing stress restarts.')
		# WARNING: if stress solution requested and second parameter in sol not -1
		if self.strs.param['ISTRS'] == 1:
			if self.sol['element_integration_INTG'] == 1:
				warnings.append('Gaussian integration scheme can cause spatial osciallations in pressure solution - try sol[\'element_integration_INTG\'] = 1 if this occurs.')
		# WARNING: instability if using zoneflux and surf output
		if self.hist.zoneflux and self.hist.type != 'tec':
			warnings.append('Use of history output format \''+self.hist.type+'\' may not be compatible with zoneflux output (fehm macro: flxz). Use \'tec\' if problems experienced.')
		# WARNING: if a co2 relperm is specified without the carb macro, there will be issues
		co2_rlpm_flag = False
		for rlpm in self.rlpmlist:
			for phase in rlpm.phases:
				if phase.startswith('co2'): co2_rlpm_flag = True
		if self.carb.iprtype == 1 and co2_rlpm_flag:
			warnings.append('Specification of co2 relperm relationship without invoking the CARB module may cause crashes.')
		# print warnings
		if warnings:
			L = 62
			print ''
			print ' !!!!---------------------------------------------------------!!!!'
			print ' !!!! Possible errors detected in input file.                 !!!!'
			print ' !!!!---------------------------------------------------------!!!!'
			for warning in warnings:
				stri = ' !!!! -'
				keepGoing = True
				warning = warning.split()
				while keepGoing:
					if not warning: 
						for i in range(L-len(stri)): stri += ' '
						print stri+'!!!!'
						stri = ' !!!! '
						break
					if len(stri)<(L-len(warning[0])): 
						stri += ' '+warning[0]
						warning = warning[1:]
					else:
						for i in range(L-len(stri)): stri += ' '
						print stri+'!!!!'
						stri = ' !!!!   '
			print ' !!!!---------------------------------------------------------!!!!'
			print ''
		return False
	def temperature_gradient(self,filename,offset=0.,first_zone = 100,auxiliary_file=None):
		'''Assign initial temperature distribution to model based on supplied temperature profile.
		
		:param filename: Name of a file containing temperature gradient data. File should be two columns, comma or space separated, with elevation in the first column and temperature (degC) in the second.
		:type filename: str
		:param offset: Vertical offset added to the elevation in temperature gradient data. Useful if model limits don't correspond to data.
		:type offset: fl64
		:param first_zone: Index of first zone created. Zone index will be incremented by 1 thereafter.
		:type first_zone: int
		:param auxiliary_file: Name of auxiliary file in which to store **PRES** macros.
		:type auxiliary_file: str
		'''
		# check if file exists
		if not os.path.isfile(filename): print 'ERROR: cannot find temperature gradient file \''+filename+'\'.'; return
		# determine uniqueness of z-coords - if less than 100, use zones, if more than 100, use nodes.
		z = np.unique([nd.position[2] for nd in self.grid.nodelist])
		if len(z) <= 100: zoneFlag = True
		else: zoneFlag = False
		# read temperature data, apply offset, extend or trim to vertical extent of model
		tempfile = open(filename,'r')
		ln = tempfile.readline()
		tempfile.close()
		commaFlag = False; spaceFlag = False
		if len(ln.split(',')) > 1: commaFlag = True
		elif len(ln.split()) > 1: spaceFlag = True
		if not commaFlag and not spaceFlag: print 'ERROR: incorrect formatting for \''+filename+'\'. Expect first column depth (m) and second column temperature (degC), either comma or space separated.'; return
		if commaFlag: tempdat = np.loadtxt(filename,delimiter=',')
		else: tempdat = np.loadtxt(filename)
		zt = tempdat[:,0]; tt = tempdat[:,1]
		zt = zt + offset
		if zt[0]>zt[-1]: zt = np.flipud(zt); tt = np.flipud(tt)
		# calculate pressure to assign
		if 0 in self.pres.keys():
			p0 = self.pres[0].param['pressure']
		else:
			p0 = 1.
			print 'WARNING: no pressure information, assigning default of 1 MPa. These pressures will be overwritten if GRAD macro used.'
		# assign zones or nodes
		if zoneFlag:
			ind = first_zone
			x0,x1 = self.grid.xmin,self.grid.xmax
			y0,y1 = self.grid.ymin,self.grid.ymax
			for zi,ti in zip(z,np.interp(z,zt,tt)):
				zn = fzone(index=ind)
				zn.rect([x0-0.1,y0-0.1,zi-0.1],[x1+0.1,y1+0.1,zi+0.1])
				self.add(zn)
				self.add(fmacro('pres',zone=ind,file = auxiliary_file, param=(('pressure',p0),('temperature',ti),('saturation',1))))
				ind +=1
		else:
			for nd,ti in zip(self.grid.nodelist,np.interp([nd.position[2] for nd in self.grid.nodelist],zt,tt)):
				self.add(fmacro('pres',zone=(nd.index,nd.index,1),file = auxiliary_file, param=(('pressure',p0),('temperature',ti),('saturation',1))))
################## ZONE FUNCTIONS
	def _read_zonn(self,infile,file=''):					#ZONE: Reads ZONE or ZONN macro.
		block = ['zone\n']
		line=infile.readline().strip(); block.append(line+'\n')
		if line[0:4]=='file':
			line = infile.readline().strip(); block.append(line+'\n')
			self._read_zonn_file(line)
		else:
			more = True
			while more:
				new_zone = fzone()
				if file: new_zone.file=file
				# assess whether zone has already been defined
				zind = int(line.split()[0])
				new_zone.index = zind
				if line.rfind('#') != -1: new_zone.name = line[line.rfind('#')+1:].strip()
				line=infile.readline().strip(); block.append(line+'\n')
				new_zone.points = []
				if line[0:4]=='list':
					new_zone.type='list'
					morePoints = True
					while morePoints:
						line=infile.readline().strip(); block.append(line+'\n')
						pts = line.split()
						if not pts: morePoints = False
						else: new_zone.nodelist.append(self.grid.node_nearest_point([float(pt) for pt in pts]))
				elif line[0:4] == 'nnum':
					new_zone.type='nnum'
					line=infile.readline().strip(); block.append(line+'\n')		
					nums = line.split()
					number_nodes = int(nums[0])					
					for num in nums[1:]: new_zone.nodelist.append(self.grid.node[int(num)])
					while (len(new_zone.nodelist)!=number_nodes):
						line=infile.readline().strip(); block.append(line+'\n')		
						nums = line.split()
						for num in nums: new_zone.nodelist.append(self.grid.node[int(num)])
				else:
					new_zone.type='rect'
					if not self.ctrl['geometry_ICNL']: 		# 3-D geometry
						numPts = 24 						# number of points to define rect
					else: 									# 2-D geometry
						numPts = 8							# number of points to define rect
					iPts = 0
					pts = line.split()
					allpts = []
					for pt in pts: allpts.append(float(pt))
					iPts += len(pts) 
					while iPts != numPts:
						line = infile.readline().strip(); block.append(line+'\n')
						pts = line.split()
						for pt in pts: allpts.append(float(pt))
						iPts += len(pts) 
					new_zone.points = np.array(list(flatten(allpts)))
					if np.size(new_zone.points)==24: 
						if self.grid.dimensions == 3: 
							new_zone.points = list(new_zone.points.reshape(3,8))
						else: 
							new_zone.points = list(new_zone.points[:16].reshape(2,8))
					else: new_zone.points = list(new_zone.points.reshape(2,4))
				# zone already defined, check if definitions match
				if zind in self.zone.keys():
					zn_old = self.zone[zind]
					if zn_old.type != new_zone.type:
						print 'WARNING: zone '+str(zind)+' was defined earlier in the input file. PyFEHM assumes unique zone definitions. This zone will be ignored.'
					elif new_zone.type == 'rect':
						x0n,x1n = np.min(new_zone.points[0]), np.max(new_zone.points[0])
						y0n,y1n = np.min(new_zone.points[1]), np.max(new_zone.points[1])
						z0n,z1n = np.min(new_zone.points[2]), np.max(new_zone.points[2])
						x0o,x1o = np.min(zn_old.points[0]), np.max(zn_old.points[0])
						y0o,y1o = np.min(zn_old.points[1]), np.max(zn_old.points[1])
						z0o,z1o = np.min(zn_old.points[2]), np.max(zn_old.points[2])
						
						if (x0n != x0o) or (x1n != x1o) or (y0n != y0o) or (y1n != y1o) or (z0n != z0o) or (z1n != z1o):
							print 'WARNING: zone '+str(zind)+' was defined earlier in the input file. PyFEHM assumes unique zone definitions. This zone will be ignored.'
					else:
						nds_old = zn_old.nodelist
						nds_new = new_zone.nodelist
						different_zone = False
						for nd in nds_old:
							if nd not in nds_new:
								different_zone = True
								break
						for nd in nds_new:
							if nd not in nds_old:
								different_zone = True
								break
						if different_zone:
							print 'WARNING: zone '+str(zind)+' was defined earlier in the input file. PyFEHM assumes unique zone definitions. This zone will be ignored.'
				
				if not zind in self.zone.keys(): self._add_zone(new_zone,overwrite=True)		
				line=infile.readline(); block.append(line+'\n')
				if not line.strip(): more = False
		return block
	def _read_zonn_file(self,file):								#Reads ZONN from specified file.
		zone_file = open(file,'r')
		line = zone_file.readline().strip()
		self._read_zonn(zone_file,file)
	def _write_zonn_all(self,outfile):							#Writes ZONE or ZONN macro.
		ws = _title_string('ZONES',72)
		outfile.write(ws)
		# check for zones specified in external files - write these first
		filezone = False
		file_zns = []
		file_nms = []
		for zn in self.zonelist:
			if zn.file: 
				filezone = True
				file_zns.append(zn)
				if zn.file not in file_nms: file_nms.append(zn.file)
		if filezone:
			for file_nm in file_nms:
				outfile.write('zonn\n')
				outfile.write('file\n')
				outfile.write(file_nm+'\n')			
				# if filename does not exist, write file
				if not os.path.isfile(file_nm):
					zonefile = open(file_nm,'w')
					zns = [zn for zn in self.zonelist if zn.file==file_nm]
					for zn in zns: zn.file = ''
					self._write_zonn_one(zonefile,zns)
					for zn in zns: zn.file = file_nm
					zonefile.write('stop\n')
					zonefile.close()	
		outfile.write('zonn\n')
		for zn in self.zonelist:
			if zn.file: continue
			if zn.index == 0: continue
			outfile.write(str(zn.index))
			if zn.name: outfile.write('\t\t#'+zn.name.strip())
			outfile.write('\n')
			if zn.type != 'rect':
				outfile.write(str(zn.type)+'\n')
			for ptarray in zn.points:
				for pt in ptarray: outfile.write(str(pt)+'\t')
				outfile.write('\n')
			if zn.type == 'list': outfile.write('\n')
		outfile.write('\n')		
	def _write_zonn_one(self,outfile,zns=[]):					#Writes out a single zone when using sticky
		if not zns: return
		uniqueZns = []
		uniqueZns_inds=[]
		for zn in zns:
			if zn.index not in uniqueZns_inds: uniqueZns_inds.append(zn.index); uniqueZns.append(zn)
		zns = uniqueZns
		# check for zones specified in external files - write these first
		filezone = False
		regzone = False
		file_zns = []
		file_nms = []
		for zn in zns:
			if isinstance(zn,tuple): continue
			if zn.file: 
				filezone = True
				file_zns.append(zn)
				if zn.file not in file_nms: file_nms.append(zn.file)
			else: regzone=True
		if filezone:
			for file_nm in file_nms:
				outfile.write('zone\n')
				outfile.write('file\n')
				outfile.write(file_nm+'\n')			
				# if filename does not exist, write file
				if not os.path.isfile(self.work_dir+file_nm) or self._writeSubFiles:
					zonefile = open(self.work_dir+file_nm,'w')
					zns = [zn for zn in self.zonelist if zn.file==file_nm]
					for zn in zns: zn.file = ''
					self._write_zonn_one(zonefile,zns)
					for zn in zns: zn.file = file_nm
					zonefile.write('stop\n')
					zonefile.close()
			return
		if not regzone: return
		outfile.write('zone\n')
		for zn in zns:
			if zn.file: continue
			else:
				if zn.index == 0: continue
				outfile.write(str(zn.index))
				if zn.name: outfile.write('\t\t#'+zn.name.strip())
				outfile.write('\n')
				if zn.type != 'rect':
					outfile.write(str(zn.type)+'\n')
				for ptarray in zn.points:
					for pt in ptarray: outfile.write(str(pt)+'\t')
					outfile.write('\n')
				if zn.type == 'list': outfile.write('\n')
		if not zn.file: outfile.write('\n')		
	def _add_zone(self,zone=fzone(),overwrite=False):			#Adds a ZONE object.
		# check if zone already exists
		if isinstance(zone,fzone):
			if zone.index in self.zone.keys():
				if not overwrite:
					print 'WARNING: A zone with index '+str(zone.index)+' already exists. Zone will not be defined, use overwrite = True in add() to overwrite the old zone.'
					return
				else:
					self.delete(self.zone[zone.index])
		
			if zone.name in self.zone.keys():
				if not overwrite:
					print 'WARNING: A zone with name \''+str(zone.name)+'\' already exists. Zone will not be defined, use overwrite = True in add() to overwrite the old zone.'
					return
				else:
					self.delete(self.zone[zone.name])
		
		zone._parent = self
		if zone not in self._zonelist:
			self._zonelist.append(zone)
		self._associate_zone(zone)
	def _associate_zone(self,zone): 							#Associates nodes contained within a ZONE, with that zone
		if not self._associate: return
		for nd in zone.nodelist:	
			nd._zone.update({zone.index:zone})
	def _delete_zone(self,zone=fzone()):
		if zone.index in [999,998,997,996,995,994]: return
		self._zonelist.remove(zone)
	def _is_zone(self,obj):		 								#Corrects index zone specification to object
		if isinstance(obj.zone,int):
			if obj.zone in self._zone_indices: 
				obj.zone = self.zone[obj.zone]
			else:
				print 'Error: zone ' + str(obj.zone) + ' does not exist.'
				return 		
		return obj
	def _get_info(self): 									#Prints out information about the data file
		# grid dimensions
		import itertools
		print '***********************************************************************'
		if self.filename: 
			print '***** '+self.filename+' *****' 	# file name
			print '***********************************************************************'		
		if self.grid.filename:												# grid properties
			print 'Model domain: x = ['+str(self.grid.xmin) + ', ' + str(self.grid.xmax) + ']'
			print '              y = ['+str(self.grid.ymin) + ', ' + str(self.grid.ymax) + ']'
			print '              z = ['+str(self.grid.zmin) + ', ' + str(self.grid.zmax) + ']'
			print '          nodes = ' +str(self.grid.number_nodes)
			print ' '
		else:
			print '%%%%% no grid associated %%%%%'
		if len(self.zonelist)==1: 										# zones
			print 'No user defined zones'
		elif len(self.zonelist)==2:
			print 'One user defined zone: '+str(self.zonelist[-1].index)
		else:
			printStr = str(len(self.zonelist)-1) +' user defined zones: '+str(self.zonelist[1].index)
			for zn in self.zonelist[2:]: printStr+=', '+str(zn.index)
			print printStr+'\n'
		if self.permlist:												# permeablities
			for perm in self.permlist: 
				if perm.zone.index==0: break
			print 'Permeability: \n    background - kx, ky, kz = ['+str(perm.param['kx'])+', '+str(perm.param['ky'])+ ', '+str(perm.param['kz'])+']'
			for perm in self.permlist:
				if perm.zone.index==0: continue
				print '    zone '+str(perm.zone.index)+' - kx, ky, kz = ['+str(perm.param['kx'])+', '+str(perm.param['ky'])+ ', '+str(perm.param['kz'])+']'			
			print ' '
		else:
			print '%%%%% no permeability properties assigned %%%%%'
		if self.condlist:												# conductivities
			for cond in self.condlist: 
				if cond.zone.index==0: break
			print 'Conductivity: \n    background - Kx, Ky, Kz = ['+str(cond.param['cond_x'])+', '+str(cond.param['cond_y'])+ ', '+str(cond.param['cond_z'])+']'
			for cond in self.condlist:
				if cond.zone.index==0: continue
				print '    zone '+str(cond.zone.index)+' - Kx, Ky, Kz = ['+str(cond.param['cond_x'])+', '+str(cond.param['cond_y'])+ ', '+str(cond.param['cond_z'])+']'
			print ' '
		else:
			print '%%%%% no conductivity properties assigned %%%%%'
		if self.rocklist:												# rock properties
			for rock in self.rocklist: 
				if rock.zone.index==0: break
			print ('Rock properties: \n    background - density = '+str(rock.param['density'])+', specific heat = '
				+str(rock.param['specific_heat'])+ ', porosity = '+str(rock.param['porosity']))
			for rock in self.rocklist:
				if rock.zone.index==0: continue
				print ('    zone '+str(rock.zone.index)+' - density = '+str(rock.param['density'])+', specific heat = '
				+str(rock.param['specific_heat'])+ ', porosity = '+str(rock.param['porosity']))
			print ' '
		else:
			print '%%%%% no rock properties assigned %%%%%'
		if self.flowlist:												# generators
			prntStr = 'Generators: \n    zone '
			for flow in self.flowlist:
				if isinstance(flow.zone,fzone):
					prntStr += str(flow.zone.index) + ' - '
				else:
					prntStr += '('+str(flow.zone[0]) + ','+str(flow.zone[1]) + ','+str(flow.zone[2]) +') - '
				prntStr += 'SKD = '+str(flow.param['rate']) + ', '
				prntStr += 'EFLOW = '+str(flow.param['energy']) + ', '
				prntStr += 'AIPED = '+str(flow.param['impedance'])
				print prntStr
				if flow.param['rate']>0:	
					if flow.param['energy']>0:
						if flow.param['impedance']==0: print '            mass production at fixed rate of ' + str(abs(flow.param['rate']))+' kg/s'
						else: print '            mass production against specified WHP of ' + str(abs(flow.param['rate'])) + ' MPa'
				else:
					if flow.param['energy']>0:
						if flow.param['impedance']==0: print '            mass injection of '+str(flow.param['energy'])+' MJ/kg fluid at fixed rate of ' + str(abs(flow.param['rate']))+' kg/s'
						else:print '            mass injection of '+str(flow.param['energy'])+' MJ/kg fluid against specified WHP of ' + str(abs(flow.param['rate']))+' MPa'
					else:
						if flow.param['impedance']==0: print '            mass injection of '+str(abs(flow.param['energy']))+' degC fluid at fixed rate of ' + str(abs(flow.param['rate']))+' kg/s'
						else:print '            mass injection of '+str(abs(flow.param['energy']))+' degC fluid against specified WHP of ' + str(abs(flow.param['rate']))+' MPa'
				prntStr = '    zone '
			print ' '
		if self.bounlist:											# flow boundary conditions
			print 'Flow boundary conditions: zone INCOMPLETE'
		if not self.flowlist and not self.bounlist and not self.co2flowlist:
			print '%%%%% no boundary conditions assigned %%%%%'
		if self.carb.iprtype !=1:		 								# co2 module
			co2model = dict([(1,'Water only'),(2,'CO2 only'),(3,'CO2-water, no solubility'),
			(4,'CO2-water, with solubility'),(5,'CO2-water-air, with solubility')])
			print 'CO2 module: ' + co2model[self.carb.iprtype]
			if self.co2flowlist:
				prntStr = '....CO2 generators: zone '
				for co2flow in self.co2flowlist:
					prntStr += (str(co2flow.zone.index) + ' - SKTMP = '+str(co2flow.param['rate'])+', ESKTMP = '+str(co2flow.param['energy'])
								+ ', AIPED = ' + str(co2flow.param['impedance']) + ', FLAG = '+str(co2flow.param['bc_flag']))
					print prntStr
					prntStr = '                  : zone '
			if self.co2fraclist:
				for co2frac in self.co2fraclist:
					if co2frac.zone.index==0: break
				print ('....Initial CO2 fractions: \n        background - water saturation = '+str(co2frac.param['water_rich_sat'])+', CO2 saturation = '+str(co2frac.param['co2_rich_sat'])
				+', CO2 mass fraction = '+str(co2frac.param['co2_mass_frac'])+', CO2 initial salt concentration = '+str(co2frac.param['init_salt_conc']))
				for co2frac in self.co2fraclist:
					if co2frac.zone.index==0: continue
					print ('                          zone - water saturation = '+str(co2frac.param['water_rich_sat'])+', CO2 saturation = '+str(co2frac.param['co2_rich_sat'])
				+', CO2 mass fraction = '+str(co2frac.param['co2_mass_frac'])+', CO2 initial salt concentration = '+str(co2frac.param['init_salt_conc']))
			if self.co2preslist:
				phase = dict([(1, 'liquid'),(2,'two phase'),(3,'vapour'),(4,'super-critical')])
				for co2pres in self.co2preslist:
					if co2pres.zone.index==0: break
				print ('....Initial CO2 conditions: \n        background - pressure = '+str(co2pres.param['pressure'])+' MPa, temperature = '+str(co2pres.param['temperature'])
				+' degC, phase = '+phase[co2pres.param['phase']])
				for co2pres in self.co2preslist:
					if co2pres.zone.index==0: continue					
					print ('                            zone - pressure = '+str(co2pres.param['pressure'])+' MPa, temperature = '+str(co2pres.param['temperature'])
					+' degC, phase = '+phase[co2pres.param['phase']])
		if self.strs.param['ISTRS']: 								# stress module
			print 'Stress module:'
			if self.elasticlist:
				for elastic in self.elasticlist: 
					if elastic.zone.index==0: break
				print '....Elastic properties: \n        background - E = '+str(elastic.param['youngs_modulus'])+' MPa, nu = '+str(elastic.param['poissons_ratio'])
				for elastic in self.elasticlist:
					if elastic.zone.index==0: continue
					print '        zone '+str(elastic.zone.index)+' - E = '+str(elastic.param['youngs_modulus'])+' MPa, nu = '+str(elastic.param['poissons_ratio'])
			else:
				print '    %%%%% no elastic properties assigned %%%%%'
			if self.biotlist:
				for biot in self.biotlist: 
					if biot.zone.index==0: break
				print '....Thermo and poroelastic properties: \n        background - thermal = '+str(biot.param['thermal_expansion'])+', pressure = '+str(biot.param['pressure_coupling'])
				for biot in self.biotlist:
					if biot.zone.index==0: continue
					print '        zone '+str(biot.zone.index)+' - thermal = '+str(biot.param['thermal_expansion'])+', pressure = '+str(biot.param['pressure_coupling'])
			else:
				print '    %%%%% no pore pressure (biot) properties assigned %%%%%'
			if self.stressbounlist:
				print '....Stress boundary conditions: '
				strsDirs = dict([(1,'x-dir'),(2,'y-dir'),(3,'z-dir')])
				for strs_boun in self.stressbounlist: 
					prntStr = '        zone '
					prntStr += str(strs_boun.zone.index) +' - '
					if strs_boun.subtype=='lithograd': 
						prntStr += 'lithograd, '
						prntStr += strsDirs[abs(strs_boun.param['direction'])]+', '
						prntStr += 'stress grad = ' + str(strs_boun.param['value']) + ' MPa/m'
					elif strs_boun.subtype == 'distributed':
						prntStr += strs_boun.subtype +' force, '	
						prntStr += strsDirs[abs(strs_boun.param['direction'])]+', '
						prntStr += str(strs_boun.param['value'])+ ' MPa'
					elif strs_boun.subtype == 'lithostatic':
						prntStr +='not done!'
					else:
						if strs_boun.param['direction']>0: prntStr += 'fixed disp, '
						else: prntStr += 'fixed force, '
						prntStr += strsDirs[abs(strs_boun.param['direction'])]+', '
						prntStr += str(strs_boun.param['value'])+' '
						if strs_boun.param['direction']>0: prntStr += 'm'
						else: prntStr += 'MPa'
					print prntStr
			else:
				print '    %%%%% no stress boundary conditions assigned %%%%%'
			if self.permmodellist:
				print '....Stress-permeability relationships:'
				for perm_model in self.permmodellist:
					if not perm_model.zone: continue
					prntStr = '        model ' + str(perm_model.index)
					if len(perm_model.zone)==1:
						prntStr += ' - zone ' + str(perm_model.zone[0].index)
					else:
						prntStr += ' - zones ' 
						for zn in perm_model.zone[:-1]: prntStr += str(zn.index) + ', '
						prntStr += str(perm_model.zone[-1].index)
					for par,unit in zip(permDicts[perm_model.index],permUnits[perm_model.index]):
						if par in perm_model.param.keys():
							prntStr +='\n            '+par+' = '+str(perm_model.param[par])+' '+unit
					if perm_model.index==1: 
						prntStr += '\n            no permeability modification'
					print prntStr
			else:
				print '    %%%%% no stress-permeability models specified %%%%%'
			print ' '
		if self.cont.variables:											# contour output
			print 'Contour output ('+self.cont.type+' format) requested for - '
			vars = list(itertools.chain(*self.cont.variables))
			for var in vars: print '    '+var
		if self.hist.variables:											# history output
			print 'History output ('+self.hist.type+' format) requested for - '			
			vars = list(itertools.chain(*self.hist.variables))
			for var in vars: print '    '+var
		if not self.cont.variables and not self.hist.variables:
			print '%%%%% no output requested %%%%%'
		print '***********************************************************************'
	what = property(_get_info)
################## MACRO FUNCTIONS
	def _read_macro(self,infile,macroName): 				#MACRO: Reads general format macros
		from copy import copy,deepcopy
		more=True
		file_flag=False
		grad_flag=True
		while more:
			if macroName not in ['permmodel','rlp']:
				m = fmacro(macroName)
				line=infile.readline().strip()
				if not line: more=False; continue		
				if line.startswith('file'): more=False; file_flag = True; continue 		# read file data
#				params = copy(dict(macro_list[macroName]))
					#vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
					#vvvvvvvvvvvvvvvvvvvv exception for stressboun vvvvvvvvvvvvvvvvvvvvvvvvv
					# assess boundary condition type									  #v
				if macroName == 'stressboun':											  #v
					m.subtype='fixed'													  #v
					if line.startswith('distributed') or line.startswith('lithostatic') or line.startswith('lithograd'):
						m.subtype=line.split()[0]										  #v
						oldline = line; line=infile.readline().strip()					  #^
					if m.subtype=='lithograd':											  #^
						m.param['sdepth']=float(oldline.split()[1])						  #^
						m.param['gdepth']=float(oldline.split()[2])						  #^
					#^^^^^^^^^^^^^^^^^^^^^^^^^^^ end exception ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
					#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
					#vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
					#vvvvvvvvvvvvvvvvvvvvvvv exception for grad vvvvvvvvvvvvvvvvvvvvvvvvvvvv
					# turn boolean 'more' into countdown								  #v
				if macroName == 'grad':													  #v
					if grad_flag:														  #v
						more = int(line.split()[0])										  #v
						grad_flag=False													  #^
						line = infile.readline().strip()								  #^
					more -= 1															  #^
					#^^^^^^^^^^^^^^^^^^^^^^^^^^^ end exception ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
					#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
				nums = line.split()
				nums_zone,nums_params = nums[:3],nums[3:]
				if macroName == 'grad': nums_zone,nums_params = nums[:1],nums[1:]
				m.zone = self._macro_zone(nums_zone)
				if infile.name != self.filename: m.file=infile.name
				for i,key in enumerate(macro_list[macroName]): m.param[key[0]] = float(nums_params[i])			
				self._add_macro(m,overwrite=True)
		if file_flag:
			line=infile.readline().strip()
			if not os.path.isfile(line):
				# check if in subdirectory with input file
				fname = self._filename.split(slash)
				if len(fname)>0:
					fn0 = ''
					for fn in fname[:-1]: fn0 += fn
					if not os.path.isfile(fn0+slash+line):
						print 'ERROR: cannot find macro file '+line
					else:
						macrofile = open(fn0+slash+line)
						line = macrofile.readline().strip()
						self._read_macro(macrofile,macroName)
						macrofile.close()
			else:
				macrofile = open(line)
				line = macrofile.readline().strip()
				self._read_macro(macrofile,macroName)
				macrofile.close()
	def _add_macro(self,macro,overwrite=False):					#Adds the macro to data file
		# check macro zone definition
		macro._parent = self
		if isinstance(macro.zone,list) and len(macro.zone)==0: macro.zone = self.zone[0] 	# assign everywhere zone
		elif isinstance(macro.zone,tuple): macro.zone = tuple([int(ls) for ls in macro.zone])
		elif isinstance(macro.zone,(int,str)):
			if macro.zone in self.zone.keys(): macro.zone = self.zone[macro.zone]
			else: print 'ERROR: Specified zone '+str(ind)+' for macro '+macro.type+' does not exist.'
		
		# check if macro already exists
		if isinstance(macro.zone,fzone):
			zn = macro.zone
			keys =  []
			for m in self._allMacro[macro.type]:
				if isinstance(m.zone,fzone):
					keys.append((m.zone.index,m))
					if m.zone.name: keys.append((m.zone.name,m))
				elif isinstance(m.zone,tuple): keys.append((m.zone,m))
			
			keys = dict(keys)
			if zn.index in keys.keys():
				if not overwrite:
					print 'WARNING: A '+macro.type+' macro for zone '+str(zn.index)+' already exists. Macro will not be defined, use overwrite = True in add() to overwrite the old macro.'
					return
				else:
					self.delete(keys[zn.index])
		
			keys =  []
			for m in self._allMacro[macro.type]:
				if isinstance(m.zone,fzone):
					keys.append((m.zone.index,m))
					if m.zone.name: keys.append((m.zone.name,m))
				elif isinstance(m.zone,tuple): keys.append((m.zone,m))
			
			keys = dict(keys)
			if zn.name in keys.keys():
				if not overwrite:
					print 'WARNING: A macro for zone \''+str(zn.name)+'\' already exists. Macro will not be defined, use overwrite = True in add() to overwrite the old macro.'
					return
				else:
					self.delete(keys[zn.name])
	
		self._allMacro[macro.type].append(macro)
		self._allMacro[macro.type].sort(key=lambda x: x.zone.index)
		self._associate_macro(macro)
	def _associate_macro(self,macro):							#Associates macro properties with nodes
		if not self._associate: return
		if isinstance(macro.zone,list):
			for zn in macro.zone:
				for nd in zn.nodelist:	
					if macro.type =='rlp': nd._rlpmodel = macro.index
					elif macro.type =='permmodel': nd._permmodel = macro.index
		elif isinstance(macro.zone,tuple):
			'placeholder'
		elif isinstance(macro.zone,fzone) or isinstance(macro.zone,int) or isinstance(macro.zone,str):
			zn = macro.zone
			if isinstance(macro.zone,int) or isinstance(macro.zone,str): zn = self.zone[zn]
			for nd in zn.nodelist:	
				#keys = macro.param.keys()
				# add material properties
				#addToNode = dict([(k,macro.param[k]) for k in keys if k in node_props])
				#nd._material.update(addToNode)
				# add generator properties
				if macro.type =='flow':
					addToNode = macro.param
					nd._generator.update(addToNode)
				if macro.type =='co2flow':
					addToNode = {'co2rate':macro.param['rate'],'co2energy':macro.param['energy'],'co2impedance':macro.param['impedance'],'co2bc_flag':macro.param['bc_flag']}
					nd._generator.update(addToNode)
				# add initial condition properties
				#if macro.type =='pres' and not self.inconfilename:
				#	addToNode = {'P':macro.param['pressure'],'T':macro.param['temperature'],'S':macro.param['saturation']}
				#	nd._variable.update(addToNode)
			zn._updateFlag = False
			if macro.type == 'pres':
				if macro.param['saturation'] == 1:
					zn.Pi = macro.param['pressure']
					zn.Ti = macro.param['temperature']
					zn.Si = 1.
				elif macro.param['saturation'] == 2:
					zn.Pi = macro.param['pressure']
					zn.Ti = tsat(macro.param['pressure'])
					zn.Si = macro.param['temperature']
				elif macro.param['saturation'] == 3:
					zn.Pi = macro.param['pressure']
					zn.Ti = macro.param['temperature']
					zn.Si = 0.
			elif macro.type == 'rock':
				zn.density = macro.param['density']
				zn.specific_heat = macro.param['specific_heat']
				zn.porosity = macro.param['porosity']
			elif macro.type == 'elastic':
				zn.youngs_modulus = macro.param['youngs_modulus']
				zn.poissons_ratio = macro.param['poissons_ratio']
			elif macro.type == 'biot':
				zn.thermal_expansion = macro.param['thermal_expansion']
				zn.pressure_coupling = macro.param['pressure_coupling']
			elif macro.type == 'cond':
				zn.conductivity = np.array([macro.param['cond_x'],macro.param['cond_x'],macro.param['cond_x']])
			elif macro.type == 'perm':
				zn.permeability = np.array([macro.param['kx'],macro.param['ky'],macro.param['kz']])
			zn._updateFlag = True
	def _delete_macro(self,macro):								#Deletes macro from data file
		self._allMacro[macro.type].remove(macro)
	def _macro_zone(self,nums):									#Assigns zone to macro dictionary
		# assumes object has members 'zone' and 'node'
		#vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
		#vvvvvvvvvvvvvvvvvvvvvvv exception for grad vvvvvvvvvvvvvvvvvvvvvvvvvvvv
		if len(nums) == 1:													  #v
			if nums[0].startswith('all'): return self.zone[0]				  #v
			else: return self.zone[abs(int(nums[0]))]						  #^
		#^^^^^^^^^^^^^^^^^^^^^^^^^^^ end exception ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
		#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
		if (nums[0] == '1' and nums[1] == '0' and nums[2] == '0') or (int(float(nums[0]))<0):
			k = _zone_ind(float(nums[0]))
			if k in self.zone.keys(): return self.zone[k]
			else: print 'ERROR: zone '+str(k)+' has not been defined'; return None
		else:
			return (int(float(nums[0])),int(float(nums[1])),int(float(nums[2])))
	def _write_macro(self,outfile,macroName):					#Writes macro dictionary to output file
		ws = _title_string(macro_titles[macroName],72)
		printToFile = False
		filemacros = []
		textmacros = []
		singlemacros = []
		for macro in self._allMacro[macroName]:
			if macro.file == -1: printToFile = True; textmacros.append(macro)
			elif macro.file: filemacros.append(macro)
			else: 
				if macro._write_one_macro: singlemacros.append(macro)
				else: textmacros.append(macro)
		if not printToFile:
			outfile.write(ws)
			if self.sticky_zones:
				zns = []
				for macro in (textmacros+filemacros):
					if isinstance(macro.zone,fzone):
						if macro.zone.index : zns.append(macro.zone)
					elif isinstance(macro.zone,list) and len(macro.zone) != 0:
						for zn in macro.zone:
							if zn.index : zns.append(zn)
				self._write_zonn_one(outfile,zns)
		if textmacros:
			outfile.write(macroName+'\n')
				#vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
				#vvvvvvvvvvvvvvvvvvvvvvv exception for grad vvvvvvvvvvvvvvvvvvvvvvvvvvvv
			if macroName == 'grad': outfile.write(str(len(self._allMacro[macroName]))+'\n')
				#^^^^^^^^^^^^^^^^^^^^^^^^^^^ end exception ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
				#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
			#for macro in self._allMacro[macroName]:
			for macro in textmacros:
				if macro.zone == 0: macro.zone = self.zone[0]
				if printToFile:
					if macro.file != - 1: continue
				elif macro.file: continue
				#vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
				#vvvvvvvvvvvvvvvvvvvv exception for stressboun vvvvvvvvvvvvvvvvvvvvvvvvv
				if macroName=='stressboun':											  #v
					if macro.subtype != 'fixed':									  #v
						outfile.write(macro.subtype+'\t')							  #v
						if macro.subtype == 'lithograd':							  #^
							outfile.write(str(macro.param['sdepth'])+'\t'+str(macro.param['gdepth'])+'\n')
						else: outfile.write('\n')									  #^
				#^^^^^^^^^^^^^^^^^^^^^^^^^^^ end exception ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
				#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
				zn = macro.zone
				if isinstance(zn,tuple):
					outfile.write(str(zn[0])+'\t'+str(zn[1])+'\t'+str(zn[2])+'\t')
				else:
				#vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
				#vvvvvvvvvvvvvvvvvvvvvvv exception for grad vvvvvvvvvvvvvvvvvvvvvvvvvvvv
					if macroName == 'grad':											  #v
						if not zn.index: outfile.write('all\t')						  #v
						else: outfile.write(str(-zn.index)+'\t') 					  #v
						macro.param['direction']=int(macro.param['direction'])		  #^
						macro.param['variable']=int(macro.param['variable'])		  #^
				#^^^^^^^^^^^^^^^^^^^^^^^^^^^ end exception ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
				#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
					else:
						if not zn.index: outfile.write(str(1)+'\t'+'0\t0\t')
						else: outfile.write(str(-zn.index)+'\t'+'0\t0\t') 
				for key in macro_list[macroName]: outfile.write(str(macro.param[key[0]])+'\t')
				if not (macroName == 'grad' and macro == self._allMacro[macroName][-1]): 
					outfile.write('\n')
				#vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
				#vvvvvvvvvvvvvvvvvvvv exception for stressboun vvvvvvvvvvvvvvvvvvvvvvvvv
				if macroName=='stressboun' and macro != self._allMacro[macroName][-1]:#v
					outfile.write('\nstressboun\n')									  #^
				#^^^^^^^^^^^^^^^^^^^^^^^^^^^ end exception ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
				#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
			outfile.write('\n')		
##########################################	
			
##########################################		
		if singlemacros:
			for macro in singlemacros:
				self._write_zonn_one(outfile,[macro.zone])
				outfile.write(macroName+'\n')
					#vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
					#vvvvvvvvvvvvvvvvvvvvvvv exception for grad vvvvvvvvvvvvvvvvvvvvvvvvvvvv
				if macroName == 'grad': outfile.write(str(len(self._allMacro[macroName]))+'\n')
					#^^^^^^^^^^^^^^^^^^^^^^^^^^^ end exception ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
					#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
				if macro.zone == 0: macro.zone = self.zone[0]
				#vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
				#vvvvvvvvvvvvvvvvvvvv exception for stressboun vvvvvvvvvvvvvvvvvvvvvvvvv
				if macroName=='stressboun':											  #v
					if macro.subtype != 'fixed':									  #v
						outfile.write(macro.subtype+'\t')							  #v
						if macro.subtype == 'lithograd':							  #^
							outfile.write(str(macro.param['sdepth'])+'\t'+str(macro.param['gdepth'])+'\n')
						else: outfile.write('\n')									  #^
				#^^^^^^^^^^^^^^^^^^^^^^^^^^^ end exception ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
				#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
				zn = macro.zone
				if isinstance(zn,tuple):
					outfile.write(str(zn[0])+'\t'+str(zn[1])+'\t'+str(zn[2])+'\t')
				else:
				#vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
				#vvvvvvvvvvvvvvvvvvvvvvv exception for grad vvvvvvvvvvvvvvvvvvvvvvvvvvvv
					if macroName == 'grad':											  #v
						if not zn.index: outfile.write('all\t')						  #v
						else: outfile.write(str(-zn.index)+'\t') 					  #v
						macro.param['direction']=int(macro.param['direction'])		  #^
						macro.param['variable']=int(macro.param['variable'])		  #^
				#^^^^^^^^^^^^^^^^^^^^^^^^^^^ end exception ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
				#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
					else:
						if not zn.index: outfile.write(str(1)+'\t'+'0\t0\t')
						else: outfile.write(str(-zn.index)+'\t'+'0\t0\t') 
				for key in macro_list[macroName]: outfile.write(str(macro.param[key[0]])+'\t')
				if not (macroName == 'grad' and macro == self._allMacro[macroName][-1]): 
					outfile.write('\n')
					outfile.write('\n')
				
##########################################	
			
##########################################		
		if filemacros and not printToFile:
			unique_fnames = []
			for macro in filemacros: 
				if macro.file not in unique_fnames: unique_fnames.append(macro.file)
			for file_nm in unique_fnames:
				outfile.write(macroName+'\n')
				outfile.write('file\n')
				outfile.write(file_nm+'\n')	
				# if filename does not exist, write file
				if not os.path.isfile(self.work_dir+file_nm) or self._writeSubFiles:
					macrofile = open(self.work_dir+file_nm,'w')
					macros = [macro for macro in self._allMacro[macroName] if macro.file==file_nm]
					for macro in macros: macro.file = -1
					self._write_macro(macrofile,macroName)
					for macro in macros: macro.file = file_nm
					macrofile.write('stop\n')
					macrofile.close()
	def _get_macro(self,macro):									#Constructs macro lists and dictionaries
		tempDict = []
		for macro in self._allMacro[macro]:
			if isinstance(macro.zone,list):
				tempDict.append((tuple(macro.zone),macro))
			elif isinstance(macro.zone,int):
				tempDict.append((macro.zone,macro))
			else:
				tempDict.append((macro.zone.index,macro))
				if isinstance(macro.zone,fzone):
					if macro.zone.name:
						tempDict.append((macro.zone.name,macro))
		return dict(tempDict)
################## MODEL FUNCTIONS
	def _read_model(self,infile,modelName): 				#MODEL: Reads general format models
		# redirect of special cases
		if modelName == 'ppor':	self._read_model_ppor(infile); return
		line = infile.readline().strip()
		models=[]
		while line != '':									# perm model specification
			nums = line.split()
			m = fmodel(modelName,index=int(nums[0]))
			parVector = [float(num) for num in nums[1:]] 	# parameter values
			#vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
			#vvvvvvvvvvvvvvvvvvvv exception for rlp model 16 vvvvvvvvvvvvvvvvvvvvvvv
			if m.type =='rlp' and m.index ==16:									  #v
				parVector = parVector[:6]+parVector[10:12]						  #^
			#^^^^^^^^^^^^^^^^^^^^^^^^^^^ end exception ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
			#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
			if m.index in model_list[modelName].keys():
				parList = model_list[modelName][m.index] 		# parameter names
			else: 	# enumerate generic parameter names
				parList = ['param'+str(i+1) for i in range(len(parVector))]
			m.param = dict(zip(parList,parVector)) 	# make dictionary
			models.append(m)
			line = infile.readline().strip()		
		line = infile.readline().strip()
		while line != '': 								# perm model zone assignments
			nums = line.split()
			models[int(nums[-1])-1].zonelist.append(self._macro_zone(nums))
			line = infile.readline().strip()
		for m in models: self._add_model(m)
	def _read_model_trac(self,infile,transverseFlag): 
		line = infile.readline().strip()
		models1 = []
		models2 = []
		while line != '':									# perm model specification
			nums = line.split()
			i1 = int(nums[0])
			nums1 = nums[1:4]
			if transverseFlag:
				if len(nums) == 8: i2 = int(nums[4]); nums2 = nums[5:]
				elif len(nums) == 7: i2 = 0; nums2 = nums[4:]
			else:
				if len(nums) == 9: i2 = int(nums[4]); nums2 = nums[5:]
				elif len(nums) == 8: i2 = 0; nums2 = nums[4:]
			# create adsorption model
			m = fmodel('adsorption',index=i1)
			parVector = [float(num) for num in nums1] 	# parameter values
			if m.index in model_list[modelName].keys():
				parList = model_list[modelName][m.index] 		# parameter names
			else: 	# enumerate generic parameter names
				parList = ['param'+str(i+1) for i in range(len(parVector))]
			m.param = dict(zip(parList,parVector)) 	# make dictionary
			models1.append(m)
			# create diffusion model
			m = fmodel('diffusion',index=i2)
			parVector = [float(num) for num in nums2] 	# parameter values
			if transverseFlag: parVector.append(None)
			if m.index in model_list[modelName].keys():
				parList = model_list[modelName][m.index] 		# parameter names
			else: 	# enumerate generic parameter names
				parList = ['param'+str(i+1) for i in range(len(parVector))]
			m.param = dict(zip(parList,parVector)) 	# make dictionary
			models2.append(m)
			line = infile.readline().strip()		
		line = infile.readline().strip()
		while line != '': 								# perm model zone assignments
			nums = line.split()
			models1[int(nums[-1])-1].zonelist.append(self._macro_zone(nums))
			models2[int(nums[-1])-1].zonelist.append(self._macro_zone(nums))
			line = infile.readline().strip()
		return (models1,models2)
	def _read_model_ppor(self,infile):
		line = infile.readline().strip()		
		nums = line.split()
		m = fmodel('ppor',index=int(nums[0]))
		
		line = infile.readline().strip()
		nums = line.split()
		m.zonelist = [self._macro_zone(nums[:3])]
		parVector = [float(num) for num in nums[3:]] 	# parameter values
		if m.index in model_list['ppor'].keys():
			parList = model_list['ppor'][m.index] 		# parameter names
		else: 	# enumerate generic parameter names
			parList = ['param'+str(i+1) for i in range(len(parVector))]
		m.param = dict(zip(parList,parVector)) 	# make dictionary
		self._add_model(m)
	def _add_model(self,model):
		model._parent = self
		if isinstance(model.zonelist,list) and len(model.zonelist)==0: model.zonelist = [self.zone[0]] 	# assign everywhere zone
		elif isinstance(model.zonelist,tuple): model.zonelist = [tuple([int(ls) for ls in model.zonelist])]
		elif isinstance(model.zonelist,(int,str)):
			if model.zonelist in self.zone.keys(): model.zonelist = [self.zone[model.zonelist]]
			else: print 'ERROR: Specified zone '+str(model.zonelist)+' for model '+model.type+' does not exist.'
		elif isinstance(model.zonelist,fzone): model.zonelist = [model.zonelist]
		newlist = []
		for zn in model.zonelist:
			if isinstance(zn,(tuple,fzone)): newlist.append(zn)
			elif zn in self.zone.keys(): newlist.append(self.zone[zn])
			else: print 'ERROR: Specified zone '+str(zn)+' for model '+model.type+' does not exist.'
		model.zonelist = newlist
		self._allModel[model.type].append(model)
		self._allModel[model.type].sort(key=lambda x: x.index)
		self._associate_model(model)
	def _associate_model(self,model):
		'placeholder'
	def _delete_model(self,model):
		self._allModel[model.type].remove(model)
	def _write_model(self,outfile,modelName):
		# redirect of special cases
		if modelName == 'ppor':	self._write_model_ppor(outfile); return
		ws = _title_string(model_titles[modelName],72)
		outfile.write(ws)
		if self.sticky_zones:
			zns = []
			for model in self._allModel[modelName]:
				if len(model.zonelist) != 0:
					for zn in model.zonelist:
						if zn.index : zns.append(zn)
			self._write_zonn_one(outfile,zns)
		
		outfile.write(modelName+'\n')
		from operator import itemgetter
		self._allModel[modelName].sort(key=lambda x: x.index)
		for model in self._allModel[modelName]:
			if model.index in model_list[modelName].keys():
				paramList = model_list[modelName][model.index] 		# parameter names
			else: 	# enumerate generic parameter names
				paramList = ['param'+str(i+1) for i in range(len(model.param.keys()))]
			outfile.write(str(model.index)+' ')
			#vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
			#vvvvvvvvvvvvvvvvvvvv exception for rlp model 16 vvvvvvvvvvvvvvvvvvvvvvv
			if model.type =='rlp' and model.index ==16:							  #v
				paramList = (parVector[:6]+['write0','write0','write0','write0']+
				parVector[-2:]+['write0','write0'])	  							  #^
			#^^^^^^^^^^^^^^^^^^^^^^^^^^^ end exception ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
			#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
			for key in paramList:
				if key in model.param.keys():
					outfile.write(str(model.param[key])+' ')
				elif key =='write0':
					outfile.write('0 ')
			outfile.write('\n')
		outfile.write('\n')
		model_count = 1
		for model in self._allModel[modelName]:
			if model.zonelist == 0: model.zonelist = [self.zonelist[0],]
			if not model.zonelist: macro_count+=1; continue
			if isinstance(model.zonelist,fzone): model.zonelist = [model.zonelist,]
			for zn in model.zonelist:
				if isinstance(zn,tuple):
					outfile.write(str(zn[0])+'\t'+str(zn[1])+'\t'+str(zn[2])+'\t')
				else:
					if not zn.index: outfile.write(str(1)+'\t'+'0\t0\t')
					else: outfile.write(str(-zn.index)+'\t'+'0\t0\t') 
				outfile.write(str(model_count)+'\n')
			model_count+=1
		outfile.write('\n')	
	def _write_model_ppor(self,outfile):
		ws = _title_string(model_titles['ppor'],72)
		outfile.write(ws)
		if self.sticky_zones:
			zns = []
			for model in self._allModel['ppor']:
				if len(model.zonelist) != 0:
					for zn in model.zonelist:
						if zn.index : zns.append(zn)
			self._write_zonn_one(outfile,zns)
		
		outfile.write('ppor'+'\n')
		from operator import itemgetter
		self._allModel['ppor'].sort(key=lambda x: x.index)
		for model in self._allModel['ppor']:
			if model.index in model_list['ppor'].keys():
				paramList = model_list['ppor'][model.index] 		# parameter names
			else: 	# enumerate generic parameter names
				paramList = ['param'+str(i+1) for i in range(len(model.param.keys()))]
			outfile.write(str(model.index)+'\n')
			zn = model.zonelist[0]
			if isinstance(zn,tuple):
				outfile.write(str(zn[0])+'\t'+str(zn[1])+'\t'+str(zn[2])+'\t')
			else:
				if not zn.index: outfile.write(str(1)+'\t'+'0\t0\t')
				else: outfile.write(str(-zn.index)+'\t'+'0\t0\t') 
			for key in paramList:
				if key in model.param.keys():
					outfile.write(str(model.param[key])+' ')
				elif key =='write0':
					outfile.write('0 ')
			outfile.write('\n')
		outfile.write('\n')	
	def _get_model(self,model):
		return dict([(m.index,m) for m in self._allModel[model]])
################## MACRO, ZONE, BOUN LISTS
	def _get_pres(self): return self._get_macro('pres')
	pres = property(_get_pres)	
	def _get_preslist(self): return self._allMacro['pres']
	preslist = property(_get_preslist)	
	def _get_perm(self): return self._get_macro('perm')
	perm = property(_get_perm) 
	def _get_permlist(self): return self._allMacro['perm']
	permlist = property(_get_permlist)	
	def _get_rock(self): return self._get_macro('rock')
	rock = property(_get_rock) 
	def _get_rocklist(self): return self._allMacro['rock']
	rocklist = property(_get_rocklist)	
	def _get_cond(self): return self._get_macro('cond')
	cond = property(_get_cond) 
	def _get_condlist(self): return self._allMacro['cond']
	condlist = property(_get_condlist)	
	def _get_grad(self): return self._get_macro('grad')
	grad = property(_get_grad) 
	def _get_gradlist(self): return self._allMacro['grad']
	gradlist = property(_get_gradlist)	
	def _get_flow(self): return self._get_macro('flow')
	flow = property(_get_flow) 
	def _get_flowlist(self): return self._allMacro['flow']
	flowlist = property(_get_flowlist)	
	def _get_hflx(self): return self._get_macro('hflx')
	hflx = property(_get_hflx) 
	def _get_hflxlist(self): return self._allMacro['hflx']
	hflxlist = property(_get_hflxlist)	
	def _get_biot(self): return self._get_macro('biot')
	biot = property(_get_biot) 
	def _get_biotlist(self): return self._allMacro['biot']
	biotlist = property(_get_biotlist)
	def _get_elastic(self): return self._get_macro('elastic')
	elastic = property(_get_elastic)
	def _get_elasticlist(self): return self._allMacro['elastic']
	elasticlist = property(_get_elasticlist)
	def _get_co2frac(self): return self._get_macro('co2frac')
	co2frac = property(_get_co2frac)
	def _get_co2fraclist(self): return self._allMacro['co2frac']
	co2fraclist = property(_get_co2fraclist)
	def _get_co2flow(self): return self._get_macro('co2flow')
	co2flow = property(_get_co2flow) 
	def _get_co2flowlist(self): return self._allMacro['co2flow']
	co2flowlist = property(_get_co2flowlist)
	def _get_co2pres(self): return self._get_macro('co2pres')
	co2pres = property(_get_co2pres)
	def _get_co2preslist(self): return self._allMacro['co2pres']
	co2preslist = property(_get_co2preslist)
	def _get_co2diff(self): return self._get_macro('co2diff')
	co2diff = property(_get_co2diff)
	def _get_co2difflist(self): return self._allMacro['co2diff']
	co2difflist = property(_get_co2difflist)	
	def _get_stressboun(self): return self._get_macro('stressboun')
	stressboun = property(_get_stressboun)
	def _get_stressbounlist(self): return self._allMacro['stressboun']
	stressbounlist = property(_get_stressbounlist)
	def _get_permmodel(self): return self._get_model('permmodel')
	permmodel = property(_get_permmodel)
	def _get_permmodellist(self): return self._allModel['permmodel']
	permmodellist = property(_get_permmodellist)
	def _get_tpor(self): return self._get_macro('tpor')
	tpor = property(_get_tpor)
	def _get_tporlist(self): return self._allMacro['tpor']
	tporlist = property(_get_tporlist)
	def _get_rlp(self): return self._get_model('rlp')
	rlp = property(_get_rlp)
	def _get_rlplist(self): return self._allModel['rlp']
	rlplist = property(_get_rlplist)
	def _get_vcon(self): return self._get_model('vcon')
	vcon = property(_get_vcon)
	def _get_vconlist(self): return self._allModel['vcon']
	vconlist = property(_get_vconlist)
	def _get_ppor(self): return self._get_model('ppor')
	ppor = property(_get_ppor)
	def _get_pporlist(self): return self._allModel['ppor']
	pporlist = property(_get_pporlist)
	def _get__zone_indices(self): return [z.index for z in self.zonelist]
	_zone_indices = property(_get__zone_indices)	
	def _get_flxo(self): 
		for i,node_pair in enumerate(self._flxo):
			nd1,nd2 = node_pair
			if isinstance(nd1,int): nd1 = self.grid.node[nd1]
			if isinstance(nd2,int): nd2 = self.grid.node[nd2]
			self._flxo[i] = (nd1,nd2)
		return self._flxo
	def _set_flxo(self,value): self._flxo = value
	flxo = property(_get_flxo, _set_flxo) #: (*lst*) List containing two-item tuples of nodal pairs for which mass flow flux to be output.
	def _get_zonelist(self): return self._zonelist
	zonelist = property(_get_zonelist)#: (*lst[fzone]*) List of zone objects in the model.
	def _get_zone(self):
		return dict([[zn.index,zn] for zn in self.zonelist]+[[zn.name,zn] for zn in self.zonelist if zn.name])
	zone = property(_get_zone)#: (*dict[fzone]*) Dictionary of zone objects, indexed by zone number or name.
	def _get_bounlist(self): return self._bounlist
	bounlist = property(_get_bounlist)#: (*lst[fzone]*) List of boundary condition objects in the model.
	def _get_rlpmlist(self): return self._rlpmlist
	rlpmlist = property(_get_rlpmlist)
	def _get_rlpm(self): return dict([(rlpm.group,rlpm) for rlpm in self._rlpmlist])
	rlpm = property(_get_rlpm)
	def _get_filename(self): return self._path.filename
	filename = property(_get_filename)#: (*str*) File name for reading and writing FEHM input text file.
	def _get_gridfilename(self): return self.grid._path.filename
	#def _set_gridfilename(self,value): self._gridfilename = value
	gridfilename = property(_get_gridfilename) #: (*str*) File name of FEHM grid file.
	def _get_inconfilename(self): return self._inconfilename
	def _set_inconfilename(self,value): self._inconfilename = value
	inconfilename = property(_get_inconfilename, _set_inconfilename) #: (*str*) File name of FEHM restart file.
	def _get_verbose(self): return self._verbose
	def _set_verbose(self,value): 
		if not(isinstance(value,bool) or value in [0,1]): print 'Boolean values only'; return
		if isinstance(value,int):
			if value == 1: value = True
			elif value == 0: value = False
		self._verbose = value
	verbose = property(_get_verbose,_set_verbose)#: (*bool*) Boolean signalling if simulation output to be printed to screen.
	def _get_sticky_zones(self): return self._sticky_zones
	def _set_sticky_zones(self,value): self._sticky_zones = value
	sticky_zones = property(_get_sticky_zones, _set_sticky_zones) #: (*bool*) If ``True`` zone definitions will be written to the input file immediately before they are used inside a macro.
	def _get_nfinv(self): return self._nfinv
	def _set_nfinv(self,value): self._nfinv = value
	nfinv = property(_get_nfinv, _set_nfinv) #: (*int*) Boolean integer calling for generation of finite element coefficients (not recommended, see macro **NFINV**).
	def _get_nobr(self): return self._nobr
	def _set_nobr(self,value): self._nobr = value
	nobr = property(_get_nobr, _set_nobr) #: (*int*) Boolean integer calling for no breaking of connections between boundary condition nodes.
	def _get_vapl(self): return self._vapl
	def _set_vapl(self,value): self._vapl = value
	vapl = property(_get_vapl, _set_vapl) #: (*int*) Boolean integer calling for vapor pressure lowering.
	def _get_adif(self): return self._adif
	def _set_adif(self,value): self._adif = value
	adif = property(_get_adif, _set_adif) #: (*int*) Air-water diffusion coefficient, used in conjuction with macro **TRAC**.
	def _get_iter(self): return self._iter
	iter = property(_get_iter) #: (*dict[fl64,int]*) Iteration parameters (see macro **ITER**).
	def _get_ctrl(self): return self._ctrl
	ctrl = property(_get_ctrl) #: (*dict[fl64,int]*) Control parameters (see macro **CTRL**).
	def _get_time(self): return self._time
	time = property(_get_time) #: (*dict[fl64,int]*) Time stepping parameters (see macro **TIME**).
	def _get_sol(self): return self._sol
	sol = property(_get_sol) #: (*dict[fl64,int]*) Solution parameters (see macro **SOL**).
	def _get_files(self): return self._files
	files = property(_get_files) #: (*files*) Simulation execution object.
	def _get_grid(self): return self._grid
	grid = property(_get_grid) #: (*fgrid*) Grid object associated with the model.
	def _get_cont(self): return self._cont
	cont = property(_get_cont) #: (*fcont*) Contour output for the model.
	def _get_strs(self): return self._strs
	strs = property(_get_strs) #: (*fstrs*) Stress module object.
	def _get_ngas(self): return self._ngas
	ngas = property(_get_ngas) #: (*fngas*) Noncondensible gas module.
	def _get_carb(self): return self._carb
	carb = property(_get_carb) #: (*fcarb*) CO2 module object.
	def _get_trac(self): return self._trac
	trac = property(_get_trac) #: (*ftrac*) Species transport module object.
	def _get_hist(self): return self._hist
	hist = property(_get_hist) #: (*fhist*) History output for the model.
	def _get_incon(self): return self._incon
	incon = property(_get_incon) #: (*fincon*) Initial conditions (restart file) associated with the model.
	def _get_work_dir(self): 
		if self._path.absolute_to_workdir: return self._path.absolute_to_workdir
		else: return ''
	def _set_work_dir(self,value): 
		self._path.update(value)
		self.grid._path.update(value)
		self.incon._path.update(value)
		try:
			os.makedirs(self.work_dir)
		except:
			pass
	work_dir = property(_get_work_dir, _set_work_dir) #: (*str*) Directory in which to store files and run simulation.
	def _get_tf(self): return self._tf
	def _set_tf(self,value): 
		self._tf = value
		self.time['max_time_TIMS'] = value
		print 'Maximum simulation time set to '+str(value)+' days.'
	tf = property(_get_tf, _set_tf) #: (*fl64*) Final simulation time (shortcut).
	def _get_ti(self): return self._ti
	def _set_ti(self,value): 
		self._ti = value
		self.time['initial_day_INITTIME'] = value
		self.time['initial_year_YEAR']=0.
		self.time['initial_month_MONTH']=0.
		print 'Initial simulation time set to '+str(value)+ 'days.'
	ti = property(_get_ti, _set_ti) #: (*fl64*) Initial simulation time (shortcut), defaults to zero.
	def _get_dti(self): return self._dti
	def _set_dti(self,value): 
		self._dti = value
		self.time['initial_timestep_DAY'] = value
		print 'Initial time step size set to '+str(value)+' days.'
	dti = property(_get_dti, _set_dti) #: (*fl64*) Initial time step size (shortcut).
	def _get_dtmin(self): return self._dtmin
	def _set_dtmin(self,value): 
		self._dtmin = value
		self.ctrl['min_timestep_DAYMIN'] = value
		print 'Minimum time step size set to '+str(value)+' days.'
	dtmin = property(_get_dtmin, _set_dtmin) #: (*fl64*) Minimum time step size (shortcut).
	def _get_dtmax(self): return self._dtmax
	def _set_dtmax(self,value): 
		self._dtmax = value
		self.ctrl['max_timestep_DAYMAX'] = value
		print 'Maximum time step size set to '+str(value)+' days.'
	dtmax = property(_get_dtmax, _set_dtmax) #: (*fl64*) Maximum time step size (shortcut).
	def _get_dtn(self): return self._dtn
	def _set_dtn(self,value): 
		value = int(value)
		self._dtn = value
		self.time['max_timestep_NSTEP'] = value
		print 'Maximum time step number set to '+str(value)+'.'
	dtn = property(_get_dtn, _set_dtn) #: (*int*) Maximum number of time steps (shortcut).
	def _get_dtx(self): return self._dtx
	def _set_dtx(self,value): 
		self._dtx = value
		self.ctrl['timestep_multiplier_AIAA'] = value
		print 'Time step multiplier set to '+str(value)+'.'
	dtx = property(_get_dtx, _set_dtx) #: (*fl64*) Time step multiplier, acceleration (shortcut).
	def _get_help(self): return self._help
	def _set_help(self,value): self._help = value
	help = property(_get_help, _set_help) #: (*fhelp*) Module for interactive assistance.
	def _get_output_times(self): return self._output_times
	def _set_output_times(self,value): 
		if isinstance(self._output_times,(int,float)): self._output_times = [self._output_times]
		if isinstance(self._output_times,(list,tuple)): self._output_times = np.array(self._output_times)
		self._times = []
		for t in self._output_times: self.change_timestepping(t)
		if np.max(self._output_times)>self.tf:
			print 'WARNING: output requested for times after the simulation end time.'
		self._output_times = value
	output_times = property(_get_output_times, _set_output_times) #: (*lst*) List of times at which FEHM should produce output.
