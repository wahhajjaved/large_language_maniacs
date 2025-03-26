"""
This submodule implements wrapper functions for dealing with pymses.
"""

from __future__ import print_function
import pymses
import os
import gc
import numpy as np

range = xrange

sink_1d_dtype = np.dtype([('id', np.int_),
                          ('mass', np.float_),
                          ('position', (np.float_, 1)),
                          ('velocity', (np.float_, 1)),
                          ('age', np.float_)])

sink_2d_dtype = np.dtype([('id', np.int_),
                          ('mass', np.float_),
                          ('position', (np.float_, 2)),
                          ('velocity', (np.float_, 2)),
                          ('age', np.float_)])

sink_3d_dtype = np.dtype([('id', np.int_),
                          ('mass', np.float_),
                          ('position', (np.float_, 3)),
                          ('velocity', (np.float_, 3)),
                          ('age', np.float_)])


def convert_dir_to_RAMSES_args(out_dir):
    """
    Takes a directory which should have format 'XXX/YYY/output_ZZZZZ'.
    Return the base path (/XXX/YYY) and output number (ZZZZZ)
    """
    base_path, base_dir = os.path.split(out_dir)
    output_OK = True
    # Check name is valid
    if not base_dir.startswith('output_'):
        output_OK = False
    elif base_dir.count('_') != 1:
        output_OK = False
    else:
        output_number = base_dir.split('_')[1]
        if not output_number.isdigit():
            output_OK = False
    if not output_OK:
        print('Output directory {} not in RAMSES '
                '(output_XXXXX) format!'.format(out_dir))
        raise ValueError()
    output_number = int(output_number)
    
    return base_path, output_number


def get_output_id(output_dir):
    """
    Find the output ID number for an output - for RAMSES this is unique
    """

    base_path, output_number = convert_dir_to_RAMSES_args(output_dir)
    
    return output_number


def load_output(output_dir):
    import ast
    import warnings
    from pymses.sources.ramses.output import Vector, Scalar
    """
    Load a RAMSES output and return the RamsesOutput object
    """
    base_path, output_number = convert_dir_to_RAMSES_args(output_dir)
    
    ro = pymses.RamsesOutput(base_path, output_number)
    
    ndim_str = str(ro.ndim)+'D'
    
    format_file = os.path.join(output_dir, 'data_info.txt')
    if os.path.isfile(format_file):
        with open(format_file) as f:
            field_descrs_str = f.readline()
        
        field_descr_in = ast.literal_eval(field_descrs_str)
        field_descr = {}
        for file_type, info_list in field_descr_in.items():
            new_info_list = []
            for item in info_list:
                if item[0] == 'Scalar':
                    new_item = Scalar(*item[1:])
                elif item[0] == 'Vector':
                    new_item = Vector(*item[1:])
                else:
                    raise ValueError('Unknown entry type '
                                     '(not Scalar or Vector)!')
                new_info_list.append(new_item)
            field_descr[file_type] = new_info_list
        
        ro.amr_field_descrs_by_file = {ndim_str: field_descr}
    
    # Read the info file ourselves because pymses does a crappy job
    # and misses interesting things
    info_file = os.path.join(
        output_dir, 'info_{0:05d}.txt'.format(output_number))
    
    with open(info_file) as f:
        lines = f.readlines()
    
    renamed_by_pymses = ['unit_l', 'unit_d', 'unit_t']
    
    for line in lines:
        if line.count('=') == 1:
            left, right = line.split('=', 1)
            if (' ' not in left.strip()) and (' ' not in right.strip()):
                name = left.strip()
                value = ast.literal_eval(right.strip())
                if (name not in ro.info) and (name not in renamed_by_pymses):
                    ro.info[name] = value
    
    # Read the sink file, if present
    sink_file = os.path.join(
        output_dir, 'sink_{0:05d}.csv'.format(output_number))
    
    if ro.ndim == 1:
        sink_dtype = sink_1d_dtype
    elif ro.ndim == 2:
        sink_dtype = sink_2d_dtype
    else:
        sink_dtype = sink_3d_dtype
    
    if os.path.isfile(sink_file):
        with open(sink_file) as f:
            warnings.filterwarnings("ignore",
                                    message="genfromtxt: Empty input file:")
            sink_data = np.genfromtxt(f, delimiter=',', dtype=sink_dtype)
            if sink_data.ndim == 0:
                # If we have a single sink, need to reshape to add dimension
                sink_data = sink_data.reshape(-1)
        ro.info['sink_data'] = sink_data
    else:
        ro.info['sink_data'] = np.array([], dtype=sink_dtype)
    
    return ro


def get_time(ro):
    """
    Take a RAMSES object and return the time
    """
    return ro.info['time']


def get_ndim(ro):
    """
    Take a RAMSES object and return the number of dimensions
    """
    return ro.info['ndim']


def get_sink_data(ro):
    """
    Take a RAMSES object and return sink data loaded earlier
    """
    return ro.info['sink_data']


def get_units(ro):
    """
    Take a RAMSES object and return a dictionary of units
    """
    from pymses.utils import constants as C
    units = {}
    for key, val in ro.info.iteritems():
        if key.startswith('unit_'):
            newkey = key[5:]
            units[newkey] = val
    units['sink_mass'] = 2e33 * C.g # Sink mass is hardcoded as 10^23g in RAMSES
    return units


def get_code_mks(units, field_name):
    """
    Use the dictionary returned by get_units and a field name to make
    an educated guess at the 'physical units' required to get back to mks.
    Calls get_code_units_guess and returns 'mks' magnitude of unit
    """
    guess = get_code_units_guess(units, field_name)
    return guess.val


def get_code_units_guess(units, field_name):
    """
    Use the dictionary returned by get_units and a field name to make
    an educated guess at the 'physical units' required to get back to mks
    """
    from pymses.utils import constants as C
    
    if field_name == 'time':
        code_mks = units['time']
    elif field_name == 'position':
        code_mks = units['length']
    elif field_name == 'rho':
        code_mks = units['density']
    elif field_name == 'vel':
        code_mks = units['velocity']
    elif field_name == 'P':
        code_mks = units['pressure']
    elif field_name == 'E_{rad}':
        code_mks = units['pressure']
    elif field_name == 'g':
        code_mks = (units['length'] / units['time']**2)
    elif field_name in units:
        code_mks = units[field_name]
    else:
        print('Unknown data type: {}'.format(field_name))
        code_mks = pymses.utils.constants.Unit((0,0,0,0,0,0), 1.0)
    
    return code_mks


def get_data_constants(ro):
    """
    Take a RAMSES object and return a dictionary of data constants
    """
    
    # List of constants, and default values if missing
    constants_list = [('mu_gas', 2.0)]
    
    constants_dict = {}
    for const_name, const_default in constants_list:
        if const_name in ro.info:
            constants_dict[const_name] = ro.info[const_name]
        else:
            constants_dict[const_name] = const_default
    
    return constants_dict


def get_minmax_res(ro):
    """
    Take a RAMSES object and return the min/maximum resolution
    """
    min_level = ro.info['levelmin']
    max_level = ro.info['levelmax']
    return 2**min_level, 2**max_level


def get_box_limits(ro):
    """
    Take a RAMSES object and get the box size
    """
    
    boxlen = ro.info['boxlen']
    #min_vals = np.zeros(ro.ndim)
    max_vals = np.zeros(ro.ndim)
    max_vals[:] = boxlen
    
    #return (min_vals, max_vals)
    return max_vals


def get_fields(ro):
    """
    Take a RAMSES object and return the list of fields
    """
    from .data import DataField
    from .data import test_field_name
    # Find possible field (depends on RAMSES format and NOT the output)
    ndim = ro.ndim
    field_descr = ro.amr_field_descrs_by_file['{}D'.format(ndim)]
    files = ro.output_files
    
    ramses_fields = []
    for file_type in field_descr:
        # Looping over 'hydro', 'grav' files
        if file_type in files:
            for field in field_descr[file_type]:
                # Looping over 'x', 'vel' etc
                new_name = field.name
                if not test_field_name(new_name):
                    new_name = new_name + '__'
                new_field = DataField(new_name)
                new_field.width = len(field.ivars)
                if len(field.ivars) == ndim:
                    new_field.flags = ['vector']
                ramses_fields.append(new_field)
    
    # Add x(,y,z) virtual fields
    new_field = DataField('position', width=ndim, flags=['position'])
    ramses_fields.insert(0, new_field)
    
    return ramses_fields


def create_field_list(fields):
    """
    Create a field list from a list of fields
    """
    from . import extra_quantities
    field_set = set()
    
    # Add field names
    for field in fields:
        if field.extra is None:
            field_set.add(field.name)
        else:
            field_set.update(extra_quantities.get_field_names(field.extra))
    
    # We don't want 'position' in our field_list
    field_set.discard('position')
    if not field_set:
        field_list = []
    else:
        field_list = list(field_set)

    return field_list


def get_cell_data(x_field, x_index, y_field, y_index,
                  data_limits, step, shared):
    """
    Obtain cell data for x_axis and y_axis, filtering with data_limits
    Neither axis is a coordinate axis
    """
    from . import extra_quantities

    # First, construct region filter - check for 'position' limits
    
    ndim = shared.ndim
    
    fields = []
    if x_field is not None:
        fields.append(x_field)
    if y_field is not None:
        fields.append(y_field)
    
    # If we are going to filter on a field, we need it!
    for limit in data_limits:
        fields.append(limit['field'])
    
    field_list = create_field_list(fields)
    
    mass_weighted = (shared.config.get('opts', 'weighting') == 'mass')
    if y_field.name == 'rho':
        mass_weighted = False
    if mass_weighted and not 'rho' in field_list:
        field_list.append('rho')
    
    # Load data, running through box filter and then creating point dataset
    amr = step.data_set.amr_source(field_list)
    region = get_region_filter(data_limits, step)
    amr_region = pymses.filters.RegionFilter(region, amr)
    cell_source = pymses.filters.CellsToPoints(amr_region)
    
    # Now, construct function filter stack
    filter_stack = function_filter_stack(cell_source, data_limits)
    
    data_array_list = []
    weights_list = []
    
    # Flatten and calculate
    for cells in filter_stack[-1].iter_dsets():
    
        # Collect data
        if x_field is None and y_field is None:
            raise ValueError('No x or y fields!')
        elif x_field is None or y_field is None:
            temp_data_array = np.zeros((cells.npoints))
            x_data_view = temp_data_array
            y_data_view = temp_data_array
        else:
            temp_data_array = np.zeros((cells.npoints, 2))
            x_data_view = temp_data_array[:, 0].view()
            y_data_view = temp_data_array[:, 1].view()
    
        if cells.npoints > 0:
            if x_field is not None:
                if x_field.extra is not None:
                    x_data_view[:] = extract_cell_func(x_field, cells)()
                else:
                    scalar = (cells[x_field.name].ndim == 1)
                    if scalar:
                        x_data_view[:] = cells[x_field.name]
                    else:
                        x_data_view[:] = cells[x_field.name][:, x_index]
            
            if y_field is not None:
                if y_field.extra is not None:
                    y_data_view[:] = extract_cell_func(y_field, cells)()
                else:
                    scalar = (cells[y_field.name].ndim == 1)
                    if scalar:
                        y_data_view[:] = cells[y_field.name]
                    else:
                        y_data_view[:] = cells[y_field.name][:, y_index]
        
        data_array_list.append(temp_data_array)
        
        if mass_weighted:
            weights_list.append(cells.get_sizes()**ndim * cells['rho'])
        else:
            weights_list.append(cells.get_sizes()**ndim)
        
        cells = None
    
    step.data_set = None
    
    if x_field is None or y_field is None:
        data_array = np.concatenate(data_array_list)
    else:
        data_array = np.vstack(data_array_list)
    data_array_list = None
    weights = np.concatenate(weights_list)
    weights_list = None
    
    return data_array, weights


def get_sample_data(x_field, x_index, xlim,
                    y_field, y_index, ylim,
                    render_field, render_index,
                    resolution, data_limits, step, shared):
    """
    Obtain sample data for x_axis and y_axis, filtering with data_limits
    """
    from . import extra_quantities
    
    multiprocessing = (shared.config.get('opts', 'multiprocessing') == 'on')

    # First, construct region filter - check for 'position' limits
    
    fields = []
    x_pos, y_pos = False, False
    if x_field is not None:
        if x_field.name == 'position':
            x_pos = True
        fields.append(x_field)
    if y_field is not None:
        if y_field.name == 'position':
            y_pos = True
        fields.append(y_field)
    
    if render_field is not None:
        # Check we have two position axes, and are in 2D
        if shared.ndim != 2:
            raise ValueError('Can only do render in get_sample_data in 2D!')
        if not (x_pos and y_pos):
            raise ValueError('Need two position axes if using render_field!')
        if render_field.name == 'position':
            raise ValueError('Cannot use position for render_field here!')
        fields.append(render_field)
    
    # If we are going to filter on a field, we need it!
    for limit in data_limits:
        fields.append(limit['field'])
    
    field_list = create_field_list(fields)
    
    mass_weighted = (shared.config.get('opts', 'weighting') == 'mass')
    if y_field.name == 'rho':
        mass_weighted = False
    if mass_weighted and not 'rho' in field_list:
        field_list.append('rho')
    
    # Get box length, coarse and fine resolution
    box_length = step.box_length
    coarse_res, fine_res = get_minmax_res(step.data_set)
    if resolution > fine_res:
        raise ValueError('Asking for more resolution than exists!')
    
    # Set up sampling points
    one_d_points = []
    for i in range(shared.ndim):
        one_d_points.append(np.linspace(0.5, resolution-0.5, resolution) /
                            resolution)
    
    if x_pos:
        xlim_sc = xlim / box_length[x_index]
        dx = xlim_sc[1] - xlim_sc[0]
        dx_fine = dx*fine_res
        x_max_points = min(dx_fine, resolution)
        if dx_fine < 1.0:
            raise ValueError('too small to sample!')
        x_step = int(2.0**np.ceil(np.log2(dx_fine/x_max_points)))
        x_res = fine_res / x_step
        x_points_full = np.linspace(0.5, x_res-0.5, x_res) * x_step / fine_res
        x_use = np.logical_and(xlim_sc[0] <= x_points_full,
                               x_points_full < xlim_sc[1])
        x_axis_points = x_points_full[x_use]
        one_d_points[x_index] = x_axis_points
        bins_x = np.empty(len(x_axis_points) + 1)
        bins_x[0:-1] = x_axis_points - (0.5 * x_step / fine_res)
        bins_x[-1] = x_axis_points[-1] + (0.5 * x_step / fine_res)
    else:
        bins_x = None
    
    if y_pos:
        ylim_sc = ylim / box_length[y_index]
        dy = ylim_sc[1] - ylim_sc[0]
        dy_fine = dy*fine_res
        y_max_points = min(dy_fine, resolution)
        if dy_fine < 1.0:
            raise ValueError('too small to sample!')
        y_step = int(2.0**np.ceil(np.log2(dy_fine/y_max_points)))
        y_res = fine_res / y_step
        y_points_full = np.linspace(0.5, y_res-0.5, y_res) * y_step / fine_res
        y_use = np.logical_and(ylim_sc[0] <= y_points_full,
                               y_points_full < ylim_sc[1])
        y_axis_points = y_points_full[y_use]
        one_d_points[y_index] = y_axis_points
        bins_y = np.empty(len(y_axis_points) + 1)
        bins_y[0:-1] = y_axis_points - (0.5 * y_step / fine_res)
        bins_y[-1] = y_axis_points[-1] + y_step / fine_res
    else:
        bins_y = None
    
    x_points = one_d_points[0]
    if shared.ndim>1:
        y_points = one_d_points[1]
    if shared.ndim>2:
        z_points = one_d_points[2]
    
    # Filter sampling points by data limits
    for limit in data_limits:
        if limit['name'] == 'position':
            index = limit['index']
            if (shared.config.get_safe('data', 'use_units') != 'off'):
                code_mks = limit['field'].code_mks
            else:
                code_mks = 1.0
            min_limit, max_limit = limit['limits']
            if min_limit != 'none':
                min_limit = min_limit / code_mks
            if max_limit != 'none':
                max_limit = max_limit / code_mks
            if index==0:
                if min_limit == 'none':
                    x_points = x_points[x_points <= max_limit]
                elif max_limit == 'none':
                    x_points = x_points[x_points >= min_limit]
                else:
                    x_points = x_points[np.logical_and(x_points >= min_limit,
                                                       x_points <= max_limit)]
                if len(x_points) == 0:
                    raise ValueError('Data limits on x axis too restrictive!')
            elif index==1:
                if min_limit == 'none':
                    y_points = y_points[y_points <= max_limit]
                elif max_limit == 'none':
                    y_points = y_points[y_points >= min_limit]
                else:
                    y_points = y_points[np.logical_and(y_points >= min_limit,
                                                       y_points <= max_limit)]
                if len(y_points) == 0:
                    raise ValueError('Data limits on y axis too restrictive!')
            elif index==2:
                if min_limit == 'none':
                    z_points = z_points[z_points <= max_limit]
                elif max_limit == 'none':
                    z_points = z_points[z_points >= min_limit]
                else:
                    z_points = z_points[np.logical_and(z_points >= min_limit,
                                                       z_points <= max_limit)]
                if len(z_points) == 0:
                    raise ValueError('Data limits on z axis too restrictive!')
    
    if (shared.ndim==1):
        points = x_points
    elif (shared.ndim==2):
        points = np.vstack(np.meshgrid(x_points,
                                       y_points)).reshape(2,-1).T
    else:
        points = np.vstack(np.meshgrid(x_points,
                                       y_points,
                                       z_points)).reshape(3,-1).T
    
    # Load data, then creating point dataset
    amr = step.data_set.amr_source(field_list)
    
    # Calculate sampled points
    sampled_dset = pymses.analysis.sample_points(amr, points,
                                                 add_cell_center=True)
                           # NOTE stupid bug in pymses means this doesn't work
                           # properly unless you have add_cell_center=True even
                           # if you don't use it
    
    # Clean up some memory
    step.data_set = None
    gc.collect()
    
    # Collect data
    if x_field is None and y_field is None:
        raise ValueError('No x or y fields!')
    elif render_field is not None:
        data_shape = (x_points.size, y_points.size)
        reversed_data_shape = tuple(reversed(data_shape))
        data_array = np.zeros(reversed_data_shape)
    elif x_field is None or y_field is None:
        data_array = np.zeros((sampled_dset.npoints))
        x_data_view = data_array
        y_data_view = data_array
    else:
        data_array = np.zeros((sampled_dset.npoints, 2))
        x_data_view = data_array[:, 0].view()
        y_data_view = data_array[:, 1].view()
    
    if sampled_dset.npoints > 0:
        if render_field is None:
            # Standard sampling
            if x_field is not None:
                if x_field.name=='position':
                    x_data_view[:] = sampled_dset.points[:, x_index]
                elif x_field.extra is not None:
                    x_data_view[:] = extract_cell_func(x_field, sampled_dset)()
                else:
                    scalar = (sampled_dset[x_field.name].ndim == 1)
                    if scalar:
                        x_data_view[:] = sampled_dset[x_field.name]
                    else:
                        x_data_view[:] = sampled_dset[x_field.name][:, x_index]
            
            if y_field is not None:
                if y_field.name=='position':
                    y_data_view[:] = sampled_dset.points[:, y_index]
                elif y_field.extra is not None:
                    y_data_view[:] = extract_cell_func(y_field, sampled_dset)()
                else:
                    scalar = (sampled_dset[y_field.name].ndim == 1)
                    if scalar:
                        y_data_view[:] = sampled_dset[y_field.name]
                    else:
                        y_data_view[:] = sampled_dset[y_field.name][:, y_index]
        
        else:
            # 2D render sampling
            if render_field.name=='position':
                data_set = sampled_dset.points[:, render_index]
            elif render_field.extra is not None:
                data_set = extract_cell_func(y_field, sampled_dset)()
            else:
                scalar = (sampled_dset[render_field.name].ndim == 1)
                if scalar:
                    data_set = sampled_dset[render_field.name]
                else:
                    data_set = sampled_dset[render_field.name][:, render_index]
            data_array[:] = data_set.reshape(reversed_data_shape)
    
        # Filter data_set, replacing data of interest with nan wherever the
        # data is outside limits
        value_limits = [x for x in data_limits if x['name'] != 'position']
        if value_limits:
            if render_field is None:
                mask = np.empty_like(x_data_view, np.bool_)
            else:
                mask = np.empty_like(data_array, np.bool_)
            mask[:] = True
            for limit in value_limits:
                name = limit['name']
                index = limit['index']
                min_f, max_f = limit['limits']
                if (shared.config.get_safe('data', 'use_units') != 'off'):
                    code_mks = limit['field'].code_mks
                else:
                    code_mks = 1.0
                if min_f != 'none':
                    min_f = min_f / code_mks
                if max_f != 'none':
                    max_f = max_f / code_mks
                print('limit: ', min_f, max_f)
                # Determine if field is scalar or vector
                if limit['width'] == 1:
                    # scalar filters
                    if min_f != 'none' and max_f != 'none':
                        filt_func = lambda dset: np.logical_and(min_f <= dset[name],
                                                dset[name] <= max_f)
                    elif min_f != 'none':
                        filt_func = lambda dset: (min_f <= dset[name])
                    elif max_f != 'none':
                        filt_func = lambda dset: (dset[name] <= max_f)
                else:
                    # vector filters
                    if min_f != 'none' and max_f != 'none':
                        filt_func = lambda dset: np.logical_and(
                            min_f <= dset[name][index], dset[name][index] <= max_f)
                    elif min_f != 'none':
                        filt_func = lambda dset: (min_f <= dset[name][index])
                    elif max_f != 'none':
                        filt_func = lambda dset: (dset[name][index] <= max_f)
                mask = np.logical_and(mask, filt_func(sampled_dset))
            if render_field is None:
                x_data_view[mask] = float('nan')
                y_data_view[mask] = float('nan')
            else:
                data_array[mask] = float('nan')
    
    if mass_weighted:
        weights = sampled_dset['rho']
    else:
        weights = np.ones(sampled_dset.npoints) #cells.get_sizes()
    
    return data_array, weights, (bins_x, bins_y)


def get_grid_data(x_field, x_index, xlim, y_field, y_index, ylim, zlim,
                  render_field, render_index, render_fac, render_transform,
                  vector_field, vector_fac, data_limits,
                  proj, resolution, z_slice, step, shared):
    """
    Obtain grid data for x_axis and y_axis, filtering with data_limits.
    """
    import math
    
    multiprocessing = (shared.config.get('opts', 'multiprocessing') == 'on')
    
    if shared.ndim!=3:
        raise ValueError('Can only do get_grid_data for 3D')
    
    # First, check for 'position' limits
    z_index = (set((0, 1, 2)) - set((x_index, y_index))).pop()
    z_axis_name = ['x', 'y', 'z'][z_index]
    up_axis_name = ['x', 'y', 'z'][y_index]
    
    if x_field.name != 'position':
        raise ValueError('x field is not a position axis!')
    if y_field.name != 'position':
        raise ValueError('y field is not a position axis!')
    
    fields = [x_field, y_field, render_field]
    if vector_field is not None:
        fields.append(vector_field)
    
    # If we are going to filter on a field, we need it!
    for limit in data_limits:
        fields.append(limit['field'])
    
    field_list = create_field_list(fields)
    
    # Get box size region from boxlen
    box_length = step.box_length
    
    # Load data
    amr = step.data_set.amr_source(field_list)
    
    # Set up box for camera
    box_min = np.zeros_like(box_length)
    #box_max = np.array(box_length)
    box_max = np.ones_like(box_length)
    
    box_min[x_index] = xlim[0] / box_length[x_index]
    box_max[x_index] = xlim[1] / box_length[x_index]
    box_min[y_index] = ylim[0] / box_length[y_index]
    box_max[y_index] = ylim[1] / box_length[y_index]
    box_centre = (box_max + box_min) / 2.0
    box_size = (box_max - box_min)
    box_size_xy = [box_size[x_index], box_size[y_index]]
    
    zlim = zlim / box_length[z_index]
    distance = 0.5 - zlim[0]
    far_cut_depth = zlim[1] - 0.5
    
    from pymses.analysis.visualization import Camera, ScalarOperator
    if render_field.width == 1:
        render_scalar = True
    else:
        render_scalar = False
    if render_field.extra is not None:
        render_func = extract_data_func(render_field)
        if render_transform is None:
            render_op = ScalarOperator(
                lambda dset: render_func(dset) * render_fac)
        else:
            render_op = ScalarOperator(
                lambda dset: render_transform[0](render_func(dset)*render_fac))
    else:
        if render_fac != 1.0:
            if render_scalar:
                if render_transform is None:
                    render_op = ScalarOperator(
                        lambda dset: render_fac * dset[render_field.name])
                else:
                    render_op = ScalarOperator(
                        lambda dset: render_transform[0](render_fac *
                            dset[render_field.name]))
            else:
                if render_transform is None:
                    render_op = ScalarOperator(
                        lambda dset: render_fac *
                            dset[render_field.name][..., render_index])
                else:
                    render_op = ScalarOperator(
                        lambda dset: render_transform[0](render_fac * 
                            dset[render_field.name][..., render_index]))
        else:
            if render_scalar:
                if render_transform is None:
                    render_op = ScalarOperator(
                        lambda dset: dset[render_field.name])
                else:
                    render_op = ScalarOperator(
                        lambda dset: render_transform[0](
                            dset[render_field.name]))
            else:
                if render_transform is None:
                    render_op = ScalarOperator(
                        lambda dset: dset[render_field.name][..., render_index])
                else:
                    render_op = ScalarOperator(
                        lambda dset: render_transform[0](
                            dset[render_field.name][..., render_index]))
    
    if proj:
        # Raytraced integrated plot
        cam = Camera(center=box_centre, line_of_sight_axis=z_axis_name,
                     region_size=box_size_xy, up_vector=up_axis_name,
                     distance=distance, far_cut_depth=far_cut_depth,
                     map_max_size=resolution, log_sensitive=False)
        from pymses.analysis.visualization.raytracing import RayTracer
        rt = RayTracer(step.data_set, field_list)
        mapped_data = rt.process(render_op, cam,
                                 multiprocessing=multiprocessing)
    else:
        # Slice map
        z_slice = (z_slice / box_length[z_index]) - 0.5
        # camera is at box centre
        
        # slice doesn't work if we are precisely along grid spacing.
        z_res = z_slice * resolution
        if z_slice==0.0:
            z_slice = z_slice + (0.01/resolution)
        elif math.fmod(z_res,1) < 0.01:
            z_slice = z_slice + ((0.01/resolution) *
                                 math.copysign(1.0, -z_slice))
        cam = Camera(center=box_centre, line_of_sight_axis=z_axis_name,
                     region_size=box_size_xy, up_vector=up_axis_name,
                     map_max_size=resolution, log_sensitive=False)
        from pymses.analysis.visualization import SliceMap
        mapped_data = SliceMap(amr, cam, render_op, z=z_slice)

    step.data_set = None
    gc.collect()

    return mapped_data.T


def get_region_filter(data_limits, step):
    """
    Create a region filter based on boxlen and data_limits
    """
    
    # Region filter seems to want positions 0 -> 1
    
    box_min = np.zeros_like(step.box_length)
    box_max = np.ones_like(box_min)
    region_limits = (box_min, box_max)
    
    if not 'position' in [x['name'] for x in data_limits]:
        return pymses.utils.regions.Box(region_limits)
    
    for limit in data_limits:
        if limit['name'] == 'position':
            index = limit['index']
            min_limit, max_limit = limit['limits']
            if (shared.config.get_safe('data', 'use_units') != 'off'):
                code_mks = limit['field'].code_mks
            else:
                code_mks = 1.0
            if min_limit != 'none':
                min_limit = min_limit / code_mks
            if max_limit != 'none':
                max_limit = max_limit / code_mks
            if min_limit != 'none':
                region_limits[0][index] = max(region_limits[0][index],
                                              min_limit)
            if max_limit != 'none':
                region_limits[1][index] = min(region_limits[1][index],
                                              max_limit)
    
    return pymses.utils.regions.Box(region_limits)


def function_filter_stack(source, data_limits):
    """
    Construct a filter stack from data limits
    """
    filter_stack = [source]
    function_filters = []
    
    for limit in data_limits:
        if limit['name'] != 'position':
            name = limit['name']
            index = limit['index']
            min_f, max_f = limit['limits']
            if (shared.config.get_safe('data', 'use_units') != 'off'):
                code_mks = limit['field'].code_mks
            else:
                code_mks = 1.0
            if min_f != 'none':
                min_f = min_f / code_mks
            if max_f != 'none':
                max_f = max_f / code_mks
            # Determine if field is scalar or vector
            if limit['width'] == 1:
                # scalar filters
                if min_f != 'none' and max_f != 'none':
                    filt_func = lambda dset: np.logical_and(min_f <= dset[name],
                                             dset[name] <= max_f)
                elif min_f != 'none':
                    filt_func = lambda dset: (min_f <= dset[name])
                elif max_f != 'none':
                    filt_func = lambda dset: (dset[name] <= max_f)
            else:
                # vector filters
                if min_f != 'none' and max_f != 'none':
                    filt_func = lambda dset: np.logical_and(
                        min_f <= dset[name][index], dset[name][index] <= max_f)
                elif min_f != 'none':
                    filt_func = lambda dset: (min_f <= dset[name][index])
                elif max_f != 'none':
                    filt_func = lambda dset: (dset[name][index] <= max_f)
            function_filters.append(filt_func)

    for filt_func in function_filters:
        new_source = pymses.filters.PointFunctionFilter(
            filt_func, filter_stack[-1])
        filter_stack.append(new_source)

    return filter_stack


def extract_cell_func(field, cells):
    """
    Extract cell data for extra quantities
    """
    from . import extra_quantities
    from . import python_math_parser
    
    # cell.points is position data
    # cell[field][:[,1:vec]] is field data
    
    lookup_table = []
    parsed = field.extra
    field_tuples = extra_quantities.get_field_tuples(parsed)
    for name, index, width in field_tuples:
        parse_string = str((name, index, width))
        if name=='position':
            parse_value = cells.points[:, index]
        else:
            #scalar = (cells[name].ndim == 1)
            if width==1:
                parse_value = cells[name]
            else:
                parse_value = cells[name][:, index]
        lookup_table.append((parse_string, parse_value))

    return python_math_parser.gen_calc(parsed, lookup_table)


def extract_data_func(field):
    """
    Extract data for extra quantities
    """
    from . import extra_quantities
    from . import python_math_parser
    
    # cell.points is position data
    # cell[field][:[,1:vec]] is field data
    
    #lambda dset: dset[render_field_name] * render_fac)
    
    lookup_table = []
    parsed = field.extra
    field_tuples = extra_quantities.get_field_tuples(parsed)
    for name, index, width in field_tuples:
        parse_string = str((name, index, width))
        if name=='position':
            def parse_value(dset, index=index):
                return dset.points[:, index]
        else:
            #scalar = (cells[name].ndim == 1)
            if width==1:
                def parse_value(dset, name=name):
                    return dset[name]
            else:
                def parse_value(dset, name=name):
                    return dset[name][..., index]
        lookup_table.append((parse_string, parse_value))

    return python_math_parser.gen_calc(parsed, lookup_table)


def add_subtract_unit(a, b):
    """
    Utility function for unit calculations: can only add or subtract
    identical quantities
    """
    if isinstance(a, float) :
        if isinstance(b, float):
            return pymses.utils.constants.Unit((0,0,0,0,0,0), 1.0)
        else:
            return b
    elif isinstance(b, float):
        return a
    elif any(a.dimensions != b.dimensions) or a.val != b.val:
        raise ValueError('Invalid unit operation: add/subtract '
                         '{} and {}!'.format(a, b))
    else:
        return a


def multiply_unit(a, b):
    """
    Utility function for unit calculations: multiply
    """
    if isinstance(a, float):
        if isinstance(b, float):
            return pymses.utils.constants.Unit((0,0,0,0,0,0), 1.0)
        else:
            return b
    elif isinstance(b, float):
        return a
    else:
        return a * b


def divide_unit(a, b):
    """
    Utility function for unit calculations: divide
    """
    if isinstance(a, float):
        if isinstance(b, float):
            return pymses.utils.constants.Unit((0,0,0,0,0,0), 1.0)
        else:
            return b
    elif isinstance(b, float):
        return a
    else:
        return a / b


def calc_units_mks(shared, field):
    """
    Run over parsed, substituting in code_mks for each field
    """
    from . import python_math_parser
    from . import extra_quantities
    
    unit_unary_dict = {'-': (lambda x: x),
                       '|': (lambda x: x)}
    unit_binary_dict = {'+': (lambda x, y: add_subtract_unit(x, y)),
                        '-': (lambda x, y: add_subtract_unit(x, y)),
                        '*': (lambda x, y: multiply_unit(x, y)),
                        '/': (lambda x, y: divide_unit(x, y)),
                        '^': (lambda x, y: x**y)}

    lookup_table = []
    parsed = field.extra
    field_tuples = extra_quantities.get_field_tuples(parsed)
    for name, index, width in field_tuples:
        parse_string = str((name, index, width))
        parse_value = get_code_units_guess(shared.sim_step_list[0].units, name)
        lookup_table.append((parse_string, parse_value))

    mks = python_math_parser.gen_calc(
        parsed, lookup_table, unary_dict=unit_unary_dict,
        binary_dict=unit_binary_dict)()
    if shared.config.get_safe('data', 'use_units') == 'off':
        field.code_mks = 1.0
    elif hasattr(mks, 'val'):
        field.code_mks = mks.val
    else:
        field.code_mks = 1.0

