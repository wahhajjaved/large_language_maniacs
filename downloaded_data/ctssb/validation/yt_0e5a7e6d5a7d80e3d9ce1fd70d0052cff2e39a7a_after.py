"""
Data structures for Athena.



"""

#-----------------------------------------------------------------------------
# Copyright (c) 2013, yt Development Team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
#-----------------------------------------------------------------------------

import h5py
import numpy as np
import weakref
import glob #ST 9/12
from yt.funcs import *
from yt.data_objects.grid_patch import \
           AMRGridPatch
from yt.geometry.grid_geometry_handler import \
    GridIndex
from yt.data_objects.static_output import \
           Dataset
from yt.utilities.definitions import \
    mpc_conversion, sec_conversion
from yt.utilities.lib.misc_utilities import \
    get_box_grids_level

from .fields import AthenaFieldInfo
from yt.units.yt_array import YTQuantity

def _get_convert(fname):
    def _conv(data):
        return data.convert(fname)
    return _conv

class AthenaGrid(AMRGridPatch):
    _id_offset = 0
    def __init__(self, id, index, level, start, dimensions):
        df = index.parameter_file.filename[4:-4]
        gname = index.grid_filenames[id]
        AMRGridPatch.__init__(self, id, filename = gname,
                              index = index)
        self.filename = gname
        self.Parent = []
        self.Children = []
        self.Level = level
        self.start_index = start.copy()
        self.stop_index = self.start_index + dimensions
        self.ActiveDimensions = dimensions.copy()

    def _setup_dx(self):
        # So first we figure out what the index is.  We don't assume
        # that dx=dy=dz , at least here.  We probably do elsewhere.
        id = self.id - self._id_offset
        if len(self.Parent) > 0:
            self.dds = self.Parent[0].dds / self.pf.refine_by
        else:
            LE, RE = self.index.grid_left_edge[id,:], \
                     self.index.grid_right_edge[id,:]
            self.dds = self.pf.arr((RE-LE)/self.ActiveDimensions, "code_length")
        if self.pf.dimensionality < 2: self.dds[1] = 1.0
        if self.pf.dimensionality < 3: self.dds[2] = 1.0
        self.field_data['dx'], self.field_data['dy'], self.field_data['dz'] = self.dds

    def __repr__(self):
        return "AthenaGrid_%04i (%s)" % (self.id, self.ActiveDimensions)

def parse_line(line, grid):
    # grid is a dictionary
    splitup = line.strip().split()
    if "vtk" in splitup:
        grid['vtk_version'] = splitup[-1]
    elif "time=" in splitup:
        time_index = splitup.index("time=")
        grid['time'] = float(splitup[time_index+1].rstrip(','))
        grid['level'] = int(splitup[time_index+3].rstrip(','))
        grid['domain'] = int(splitup[time_index+5].rstrip(','))                        
    elif "DIMENSIONS" in splitup:
        grid['dimensions'] = np.array(splitup[-3:]).astype('int')
    elif "ORIGIN" in splitup:
        grid['left_edge'] = np.array(splitup[-3:]).astype('float64')
    elif "SPACING" in splitup:
        grid['dds'] = np.array(splitup[-3:]).astype('float64')
    elif "CELL_DATA" in splitup:
        grid["ncells"] = int(splitup[-1])
    elif "SCALARS" in splitup:
        field = splitup[1]
        grid['read_field'] = field
        grid['read_type'] = 'scalar'
    elif "VECTORS" in splitup:
        field = splitup[1]
        grid['read_field'] = field
        grid['read_type'] = 'vector'

class AthenaHierarchy(GridIndex):

    grid = AthenaGrid
    _dataset_type='athena'
    _data_file = None
    
    def __init__(self, pf, dataset_type='athena'):
        self.parameter_file = weakref.proxy(pf)
        self.directory = os.path.dirname(self.parameter_file.filename)
        self.dataset_type = dataset_type
        # for now, the index file is the parameter file!
        self.index_filename = self.parameter_file.filename
        #self.directory = os.path.dirname(self.index_filename)
        self._fhandle = file(self.index_filename,'rb')
        GridIndex.__init__(self, pf, dataset_type)

        self._fhandle.close()

    def _detect_output_fields(self):
        field_map = {}
        f = open(self.index_filename,'rb')
        def check_readline(fl):
            line = fl.readline()
            if "SCALARS" in line and not line.startswith("SCALARS"):
                line = line[line.find("SCALARS"):]
            if "VECTORS" in line and not line.startswith("VECTORS"):
                line = line[line.find("VECTORS"):]
            return line
        line = check_readline(f)
        while line != '':
            splitup = line.strip().split()
            if "DIMENSIONS" in splitup:
                grid_dims = np.array(splitup[-3:]).astype('int')
                line = check_readline(f)
            elif "CELL_DATA" in splitup:
                grid_ncells = int(splitup[-1])
                line = check_readline(f)
                if np.prod(grid_dims) != grid_ncells:
                    grid_dims -= 1
                    grid_dims[grid_dims==0]=1
                if np.prod(grid_dims) != grid_ncells:
                    mylog.error('product of dimensions %i not equal to number of cells %i' %
                          (np.prod(grid_dims), grid_ncells))
                    raise TypeError
                break
            else:
                line = check_readline(f)
        read_table = False
        read_table_offset = f.tell()
        while line != '':
            splitup = line.strip().split()
            if 'SCALARS' in line and 'SCALARS' not in splitup:
                splitup = line[line.find('SCALARS'):].strip().split()
            if 'VECTORS' in line and 'VECTORS' not in splitup:
                splitup = line[line.find('VECTORS'):].strip().split()
            if 'SCALARS' in splitup:
                field = ("athena", splitup[1])
                if not read_table:
                    line = check_readline(f) # Read the lookup table line
                    read_table = True
                field_map[field] = ('scalar', f.tell() - read_table_offset)
                read_table=False

            elif 'VECTORS' in splitup:
                field = splitup[1]
                for ax in 'xyz':
                    field_map[("athena","%s_%s" % (field, ax))] =\
                            ('vector', f.tell() - read_table_offset)
            line = check_readline(f)

        f.close()

        self.field_list = field_map.keys()
        self._field_map = field_map

    def _count_grids(self):
        self.num_grids = self.parameter_file.nvtk

    def _parse_index(self):
        f = open(self.index_filename,'rb')
        grid = {}
        grid['read_field'] = None
        grid['read_type'] = None
        table_read=False
        line = f.readline()
        while grid['read_field'] is None:
            parse_line(line, grid)
            if "SCALAR" in line.strip().split():
                break
            if "VECTOR" in line.strip().split():
                break
            if 'TABLE' in line.strip().split():
                break
            if len(line) == 0: break
            line = f.readline()
        f.close()

        # It seems some datasets have a mismatch between ncells and 
        # the actual grid dimensions.
        if np.prod(grid['dimensions']) != grid['ncells']:
            grid['dimensions'] -= 1
            grid['dimensions'][grid['dimensions']==0]=1
        if np.prod(grid['dimensions']) != grid['ncells']:
            mylog.error('product of dimensions %i not equal to number of cells %i' % 
                  (np.prod(grid['dimensions']), grid['ncells']))
            raise TypeError

        # Need to determine how many grids: self.num_grids
        dataset_dir = os.path.dirname(self.index_filename)
        dname = os.path.split(self.index_filename)[-1]
        if dataset_dir.endswith("id0"):
            dname = "id0/"+dname
            dataset_dir = dataset_dir[:-3]
                        
        gridlistread = glob.glob(os.path.join(dataset_dir, 'id*/%s-id*%s' % (dname[4:-9],dname[-9:])))
        gridlistread.insert(0,self.index_filename)
        if 'id0' in dname :
            gridlistread += glob.glob(os.path.join(dataset_dir, 'id*/lev*/%s*-lev*%s' % (dname[4:-9],dname[-9:])))
        else :
            gridlistread += glob.glob(os.path.join(dataset_dir, 'lev*/%s*-lev*%s' % (dname[:-9],dname[-9:])))
        ndots = dname.count(".")
        gridlistread = [fn for fn in gridlistread if os.path.basename(fn).count(".") == ndots]
        self.num_grids = len(gridlistread)
        dxs=[]
        self.grids = np.empty(self.num_grids, dtype='object')
        levels = np.zeros(self.num_grids, dtype='int32')
        glis = np.empty((self.num_grids,3), dtype='float64')
        gdds = np.empty((self.num_grids,3), dtype='float64')
        gdims = np.ones_like(glis)
        j = 0
        self.grid_filenames = gridlistread
        while j < (self.num_grids):
            f = open(gridlistread[j],'rb')
            gridread = {}
            gridread['read_field'] = None
            gridread['read_type'] = None
            table_read=False
            line = f.readline()
            while gridread['read_field'] is None:
                parse_line(line, gridread)
                if "SCALAR" in line.strip().split():
                    break
                if "VECTOR" in line.strip().split():
                    break 
                if 'TABLE' in line.strip().split():
                    break
                if len(line) == 0: break
                line = f.readline()
            f.close()
            levels[j] = gridread['level']
            glis[j,0] = gridread['left_edge'][0]
            glis[j,1] = gridread['left_edge'][1]
            glis[j,2] = gridread['left_edge'][2]
            # It seems some datasets have a mismatch between ncells and 
            # the actual grid dimensions.
            if np.prod(gridread['dimensions']) != gridread['ncells']:
                gridread['dimensions'] -= 1
                gridread['dimensions'][gridread['dimensions']==0]=1
            if np.prod(gridread['dimensions']) != gridread['ncells']:
                mylog.error('product of dimensions %i not equal to number of cells %i' % 
                      (np.prod(gridread['dimensions']), gridread['ncells']))
                raise TypeError
            gdims[j,0] = gridread['dimensions'][0]
            gdims[j,1] = gridread['dimensions'][1]
            gdims[j,2] = gridread['dimensions'][2]
            # Setting dds=1 for non-active dimensions in 1D/2D datasets
            gridread['dds'][gridread['dimensions']==1] = 1.
            gdds[j,:] = gridread['dds']
            
            j=j+1

        gres = glis + gdims*gdds
        # Now we convert the glis, which were left edges (floats), to indices 
        # from the domain left edge.  Then we do a bunch of fixing now that we
        # know the extent of all the grids. 
        glis = np.round((glis - self.parameter_file.domain_left_edge.ndarray_view())/gdds).astype('int')
        new_dre = np.max(gres,axis=0)
        self.parameter_file.domain_right_edge[:] = np.round(new_dre, decimals=12)[:]
        self.parameter_file.domain_width = \
                (self.parameter_file.domain_right_edge - 
                 self.parameter_file.domain_left_edge)
        self.parameter_file.domain_center = \
                0.5*(self.parameter_file.domain_left_edge + 
                     self.parameter_file.domain_right_edge)
        self.parameter_file.domain_dimensions = \
                np.round(self.parameter_file.domain_width/gdds[0]).astype('int')

        # Need to reset the units in the parameter file based on the correct
        # domain left/right/dimensions.
        self.parameter_file._set_code_unit_attributes()

        if self.parameter_file.dimensionality <= 2 :
            self.parameter_file.domain_dimensions[2] = np.int(1)
        if self.parameter_file.dimensionality == 1 :
            self.parameter_file.domain_dimensions[1] = np.int(1)
        for i in range(levels.shape[0]):
            self.grids[i] = self.grid(i,self,levels[i],
                                      glis[i],
                                      gdims[i])
            dx = (self.parameter_file.domain_right_edge-
                  self.parameter_file.domain_left_edge)/self.parameter_file.domain_dimensions
            dx = dx/self.parameter_file.refine_by**(levels[i])
            dxs.append(dx)

        dx = self.pf.arr(dxs, "code_length")
        dle = self.parameter_file.domain_left_edge
        dre = self.parameter_file.domain_right_edge
        self.grid_left_edge = self.pf.arr(np.round(dle + dx*glis, decimals=12), "code_length")
        self.grid_dimensions = gdims.astype("int32")
        self.grid_right_edge = self.pf.arr(np.round(self.grid_left_edge +
                                                    dx*self.grid_dimensions,
                                                    decimals=12),
                                            "code_length")
        
        if self.parameter_file.dimensionality <= 2:
            self.grid_right_edge[:,2] = dre[2]
        if self.parameter_file.dimensionality == 1:
            self.grid_right_edge[:,1:] = dre[1:]
        self.grid_particle_count = np.zeros([self.num_grids, 1], dtype='int64')

    def _populate_grid_objects(self):
        for g in self.grids:
            g._prepare_grid()
            g._setup_dx()
        self._reconstruct_parent_child()
        self.max_level = self.grid_levels.max()

    def _reconstruct_parent_child(self):
        mask = np.empty(len(self.grids), dtype='int32')
        mylog.debug("First pass; identifying child grids")
        for i, grid in enumerate(self.grids):
            get_box_grids_level(self.grid_left_edge[i,:],
                                self.grid_right_edge[i,:],
                                self.grid_levels[i] + 1,
                                self.grid_left_edge, self.grid_right_edge,
                                self.grid_levels, mask)
                #ids = np.where(mask.astype("bool")) # where is a tuple
                #mask[ids] = True
            grid.Children = [g for g in self.grids[mask.astype("bool")] if g.Level == grid.Level + 1]
        mylog.debug("Second pass; identifying parents")
        for i, grid in enumerate(self.grids): # Second pass
            for child in grid.Children:
                child.Parent.append(grid)

    def _get_grid_children(self, grid):
        mask = np.zeros(self.num_grids, dtype='bool')
        grids, grid_ind = self.get_box_grids(grid.LeftEdge, grid.RightEdge)
        mask[grid_ind] = True
        return [g for g in self.grids[mask] if g.Level == grid.Level + 1]

class AthenaDataset(Dataset):
    _index_class = AthenaHierarchy
    _field_info_class = AthenaFieldInfo
    _dataset_type = "athena"

    def __init__(self, filename, dataset_type='athena',
                 storage_filename=None, parameters=None):
        self.fluid_types += ("athena",)
        if parameters is None:
            parameters = {}
        self.specified_parameters = parameters
        Dataset.__init__(self, filename, dataset_type)
        self.filename = filename
        if storage_filename is None:
            storage_filename = '%s.yt' % filename.split('/')[-1]
        self.storage_filename = storage_filename
        # Unfortunately we now have to mandate that the index gets 
        # instantiated so that we can make sure we have the correct left 
        # and right domain edges.
        self.h

    def _set_code_unit_attributes(self):
        """
        Generates the conversion to various physical _units based on the parameter file
        """
        for unit, cgs in [("length", "cm"), ("time", "s"), ("mass", "g")]:
            val = self.specified_parameters.get("%s_unit" % unit, None)
            if val is None:
                self.no_cgs_equiv_length = True
                mylog.warning("No %s conversion to cgs provided.  " +
                              "Assuming 1.0 = 1.0 %s", unit, cgs)
                val = 1.0
            if not isinstance(val, tuple):
                val = (val, cgs)
            setattr(self, "%s_unit" % unit, self.quan(val[0], val[1]))
        self.velocity_unit = self.length_unit/self.time_unit
        self.magnetic_unit = np.sqrt(4*np.pi * self.mass_unit /
                                  (self.time_unit**2 * self.length_unit))
        self.magnetic_unit.convert_to_units("gauss")

    def set_code_units(self):
        super(AthenaDataset, self).set_code_units()
        self.unit_registry.modify("code_magnetic", self.magnetic_unit)

    def _parse_parameter_file(self):
        self._handle = open(self.parameter_filename, "rb")
        # Read the start of a grid to get simulation parameters.
        grid = {}
        grid['read_field'] = None
        line = self._handle.readline()
        while grid['read_field'] is None:
            parse_line(line, grid)
            if "SCALAR" in line.strip().split():
                break
            if "VECTOR" in line.strip().split():
                break
            if 'TABLE' in line.strip().split():
                break
            if len(line) == 0: break
            line = self._handle.readline()

        self.domain_left_edge = grid['left_edge']
        mylog.info("Temporarily setting domain_right_edge = -domain_left_edge."+
                  " This will be corrected automatically if it is not the case.")
        self.domain_right_edge = -self.domain_left_edge
        self.domain_width = self.domain_right_edge-self.domain_left_edge
        self.domain_dimensions = np.round(self.domain_width/grid['dds']).astype('int32')
        refine_by = None
        if refine_by is None: refine_by = 2
        self.refine_by = refine_by
        dimensionality = 3
        if grid['dimensions'][2] == 1 :
            dimensionality = 2
        if grid['dimensions'][1] == 1 :
            dimensionality = 1
        if dimensionality <= 2 : self.domain_dimensions[2] = np.int32(1)
        if dimensionality == 1 : self.domain_dimensions[1] = np.int32(1)
        self.dimensionality = dimensionality
        self.current_time = grid["time"]
        self.unique_identifier = self.parameter_filename.__hash__()
        self.cosmological_simulation = False
        self.num_ghost_zones = 0
        self.field_ordering = 'fortran'
        self.boundary_conditions = [1]*6
        if 'periodicity' in self.specified_parameters:
            self.periodicity = ensure_tuple(self.specified_parameters['periodicity'])
        else:
            self.periodicity = (True,True,True,)
        if 'gamma' in self.specified_parameters:
            self.gamma = float(self.specified_parameters['gamma'])
        else:
            self.gamma = 5./3.
        dataset_dir = os.path.dirname(self.parameter_filename)
        dname = os.path.split(self.parameter_filename)[-1]
        if dataset_dir.endswith("id0"):
            dname = "id0/"+dname
            dataset_dir = dataset_dir[:-3]
            
        gridlistread = glob.glob(os.path.join(dataset_dir, 'id*/%s-id*%s' % (dname[4:-9],dname[-9:])))
        if 'id0' in dname :
            gridlistread += glob.glob(os.path.join(dataset_dir, 'id*/lev*/%s*-lev*%s' % (dname[4:-9],dname[-9:])))
        else :
            gridlistread += glob.glob(os.path.join(dataset_dir, 'lev*/%s*-lev*%s' % (dname[:-9],dname[-9:])))
        ndots = dname.count(".")
        gridlistread = [fn for fn in gridlistread if os.path.basename(fn).count(".") == ndots]
        self.nvtk = len(gridlistread)+1 

        self.current_redshift = self.omega_lambda = self.omega_matter = \
            self.hubble_constant = self.cosmological_simulation = 0.0
        self.parameters['Time'] = self.current_time # Hardcode time conversion for now.
        self.parameters["HydroMethod"] = 0 # Hardcode for now until field staggering is supported.
        if self.specified_parameters.has_key("gamma") :
            self.parameters["Gamma"] = self.specified_parameters["gamma"]
        else :
            self.parameters["Gamma"] = 5./3. 
        self.geometry = self.specified_parameters.get("geometry", "cartesian")
        self._handle.close()


    @classmethod
    def _is_valid(self, *args, **kwargs):
        try:
            if 'vtk' in args[0]:
                return True
        except:
            pass
        return False

    @property
    def _skip_cache(self):
        return True

    def __repr__(self):
        return self.basename.rsplit(".", 1)[0]

